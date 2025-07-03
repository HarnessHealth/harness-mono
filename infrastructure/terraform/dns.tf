# Route53 Hosted Zone for harness.health
resource "aws_route53_zone" "harness" {
  name = "harness.health"
  
  tags = {
    Name = "harness.health"
  }
}

# ACM Certificate for SSL/TLS
resource "aws_acm_certificate" "harness" {
  domain_name               = "harness.health"
  subject_alternative_names = ["*.harness.health", "www.harness.health", "api.harness.health", "admin.harness.health"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "harness.health"
  }
}

# DNS validation records for ACM
resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.harness.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = aws_route53_zone.harness.zone_id
}

# Certificate validation
resource "aws_acm_certificate_validation" "harness" {
  certificate_arn         = aws_acm_certificate.harness.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}

# A records for main domain (will point to ALB once created)
resource "aws_route53_record" "root" {
  zone_id = aws_route53_zone.harness.zone_id
  name    = "harness.health"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

# www subdomain
resource "aws_route53_record" "www" {
  zone_id = aws_route53_zone.harness.zone_id
  name    = "www.harness.health"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

# API subdomain
resource "aws_route53_record" "api" {
  zone_id = aws_route53_zone.harness.zone_id
  name    = "api.harness.health"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

# Admin subdomain is configured in admin_frontend.tf to point to CloudFront

# Output nameservers for domain registrar
output "nameservers" {
  description = "Nameservers to configure at your domain registrar"
  value       = aws_route53_zone.harness.name_servers
}