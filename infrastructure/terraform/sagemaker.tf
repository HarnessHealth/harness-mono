# SageMaker resources for MedGemma model deployment

# IAM role for SageMaker execution
resource "aws_iam_role" "sagemaker_execution_role" {
  name = "${var.project_name}-sagemaker-execution-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "sagemaker.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-sagemaker-execution-role-${var.environment}"
    Environment = var.environment
  }
}

# IAM policy for SageMaker execution role
resource "aws_iam_role_policy" "sagemaker_execution_policy" {
  name = "${var.project_name}-sagemaker-execution-policy"
  role = aws_iam_role.sagemaker_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sagemaker:*",
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
          "logs:PutLogEvents",
          "logs:GetLogEvents"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.models.arn,
          "${aws_s3_bucket.models.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:ListMetrics"
        ]
        Resource = "*"
      }
    ]
  })
}

# S3 bucket for SageMaker models (if not already exists)
resource "aws_s3_bucket" "models" {
  bucket = "${var.project_name}-models-${data.aws_caller_identity.current.account_id}"
  
  tags = {
    Name = "${var.project_name}-models"
    Environment = var.environment
  }
}

resource "aws_s3_bucket_versioning" "models" {
  bucket = aws_s3_bucket.models.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "models" {
  bucket = aws_s3_bucket.models.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# CloudWatch log group for SageMaker
resource "aws_cloudwatch_log_group" "sagemaker" {
  name              = "/aws/sagemaker/${var.project_name}-${var.environment}"
  retention_in_days = 14

  tags = {
    Name = "${var.project_name}-sagemaker-logs"
    Environment = var.environment
  }
}

# SageMaker domain for notebook instances (optional)
resource "aws_sagemaker_domain" "main" {
  count       = var.environment == "development" ? 1 : 0
  domain_name = "${var.project_name}-${var.environment}"
  auth_mode   = "IAM"
  vpc_id      = aws_vpc.main.id
  subnet_ids  = aws_subnet.private[*].id

  default_user_settings {
    execution_role = aws_iam_role.sagemaker_execution_role.arn
    
    jupyter_server_app_settings {
      default_resource_spec {
        instance_type       = "ml.t3.medium"
        sagemaker_image_arn = "arn:aws:sagemaker:${var.aws_region}:081325390199:image/datascience-1.0"
      }
    }
    
    kernel_gateway_app_settings {
      default_resource_spec {
        instance_type       = "ml.t3.medium"
        sagemaker_image_arn = "arn:aws:sagemaker:${var.aws_region}:081325390199:image/datascience-1.0"
      }
    }
  }

  tags = {
    Name = "${var.project_name}-sagemaker-domain"
    Environment = var.environment
  }
}

# Output the SageMaker execution role ARN
output "sagemaker_execution_role_arn" {
  description = "ARN of the SageMaker execution role"
  value       = aws_iam_role.sagemaker_execution_role.arn
}

output "sagemaker_models_bucket" {
  description = "S3 bucket for SageMaker models"
  value       = aws_s3_bucket.models.bucket
}

output "sagemaker_domain_id" {
  description = "SageMaker domain ID (development only)"
  value       = var.environment == "development" ? aws_sagemaker_domain.main[0].id : null
}