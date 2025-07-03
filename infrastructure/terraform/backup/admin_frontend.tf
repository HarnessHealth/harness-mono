# Admin Frontend Infrastructure

# S3 bucket for admin frontend static files
resource "aws_s3_bucket" "admin_frontend" {
  bucket = "${var.project_name}-admin-frontend-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

# S3 bucket for CloudFront access logs
resource "aws_s3_bucket" "admin_frontend_logs" {
  bucket = "${var.project_name}-admin-frontend-logs-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_ownership_controls" "admin_frontend_logs" {
  bucket = aws_s3_bucket.admin_frontend_logs.id

  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_acl" "admin_frontend_logs" {
  depends_on = [aws_s3_bucket_ownership_controls.admin_frontend_logs]
  bucket     = aws_s3_bucket.admin_frontend_logs.id
  acl        = "log-delivery-write"
}

resource "aws_s3_bucket_versioning" "admin_frontend" {
  bucket = aws_s3_bucket.admin_frontend.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "admin_frontend" {
  bucket = aws_s3_bucket.admin_frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block public access to the bucket (CloudFront will access it)
resource "aws_s3_bucket_public_access_block" "admin_frontend" {
  bucket = aws_s3_bucket.admin_frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CloudFront Origin Access Control
resource "aws_cloudfront_origin_access_control" "admin_frontend" {
  name                              = "${var.project_name}-admin-frontend-${var.environment}"
  description                       = "Origin Access Control for Admin Frontend"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# CloudFront distribution for admin frontend
resource "aws_cloudfront_distribution" "admin_frontend" {
  aliases = ["admin.harness.health"]

  origin {
    domain_name              = aws_s3_bucket.admin_frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.admin_frontend.id
    origin_id                = "S3-${aws_s3_bucket.admin_frontend.bucket}"
  }

  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"

  default_cache_behavior {
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "S3-${aws_s3_bucket.admin_frontend.bucket}"
    compress               = true
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 3600
    max_ttl     = 86400
  }

  # Cache behavior for static assets (JS, CSS, images)
  ordered_cache_behavior {
    path_pattern     = "*.js"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD", "OPTIONS"]
    target_origin_id = "S3-${aws_s3_bucket.admin_frontend.bucket}"
    compress         = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl                = 0
    default_ttl            = 31536000  # 1 year
    max_ttl                = 31536000  # 1 year
    viewer_protocol_policy = "redirect-to-https"
  }

  ordered_cache_behavior {
    path_pattern     = "*.css"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD", "OPTIONS"]
    target_origin_id = "S3-${aws_s3_bucket.admin_frontend.bucket}"
    compress         = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl                = 0
    default_ttl            = 31536000  # 1 year
    max_ttl                = 31536000  # 1 year
    viewer_protocol_policy = "redirect-to-https"
  }

  # Cache behavior for images and other assets
  ordered_cache_behavior {
    path_pattern     = "assets/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD", "OPTIONS"]
    target_origin_id = "S3-${aws_s3_bucket.admin_frontend.bucket}"
    compress         = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl                = 0
    default_ttl            = 604800    # 1 week
    max_ttl                = 31536000  # 1 year
    viewer_protocol_policy = "redirect-to-https"
  }

  # Custom error pages for SPA routing
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  price_class = "PriceClass_100"

  logging_config {
    include_cookies = false
    bucket          = aws_s3_bucket.admin_frontend_logs.bucket_domain_name
    prefix          = "cloudfront-logs/"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate.harness.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = {
    Name = "${var.project_name}-admin-frontend-${var.environment}"
  }
}

# S3 bucket policy for CloudFront access
resource "aws_s3_bucket_policy" "admin_frontend" {
  bucket = aws_s3_bucket.admin_frontend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowCloudFrontServicePrincipal"
        Effect    = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.admin_frontend.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.admin_frontend.arn
          }
        }
      }
    ]
  })
}

# Route53 record for admin subdomain
resource "aws_route53_record" "admin_frontend" {
  zone_id = aws_route53_zone.harness.zone_id
  name    = "admin.harness.health"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.admin_frontend.domain_name
    zone_id                = aws_cloudfront_distribution.admin_frontend.hosted_zone_id
    evaluate_target_health = false
  }
}