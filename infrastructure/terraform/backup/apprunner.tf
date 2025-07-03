# AWS App Runner service for backend API
resource "aws_apprunner_service" "api" {
  service_name = "${var.project_name}-api-${var.environment}"

  source_configuration {
    # GitHub source configuration
    code_repository {
      repository_url = "https://github.com/HarnessHealth/harness-mono"
      
      code_configuration {
        configuration_source = "REPOSITORY"  # Use apprunner.yaml from repo
        
        code_configuration_values {
          runtime                 = "PYTHON_3"
          build_command          = "pip install poetry && poetry config virtualenvs.create false && poetry install --only=main --no-dev"
          start_command          = "poetry run uvicorn backend.api.main:app --host 0.0.0.0 --port 8000"
          runtime_environment_variables = {
            PORT                    = "8000"
            PYTHONPATH             = "/opt/app"
            DATABASE_URL           = "postgresql://${var.db_username}:${random_password.harness_db.result}@${aws_db_instance.harness.endpoint}:5432/${var.db_name}"
            REDIS_URL              = "redis://${aws_elasticache_cluster.harness.cache_nodes[0].address}:6379"
            ENVIRONMENT            = var.environment
            S3_BUCKET_CORPUS       = aws_s3_bucket.veterinary_corpus.bucket
            S3_BUCKET_EMBEDDINGS   = aws_s3_bucket.embeddings.bucket
            HUGGINGFACE_ACCESS_TOKEN = var.huggingface_access_token
            WEAVIATE_URL           = "http://${aws_instance.weaviate.private_ip}:8080"
          }
          runtime_environment_secrets = {
            # Secrets will be managed separately if needed
          }
        }
      }
      
      source_code_version {
        type  = "BRANCH"
        value = "master"
      }
    }
    
    auto_deployments_enabled = true
  }

  # Instance configuration
  instance_configuration {
    cpu    = "0.25 vCPU"
    memory = "0.5 GB"
    instance_role_arn = aws_iam_role.apprunner_instance.arn
  }

  # Auto scaling configuration
  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.api.arn

  # Health check configuration
  health_check_configuration {
    healthy_threshold   = 1
    interval           = 10
    path               = "/api/health"
    protocol           = "HTTP"
    timeout            = 5
    unhealthy_threshold = 5
  }

  # Network configuration for VPC access
  network_configuration {
    egress_configuration {
      egress_type       = "VPC"
      vpc_connector_arn = aws_apprunner_vpc_connector.main.arn
    }
  }

  tags = {
    Name        = "${var.project_name}-api-${var.environment}"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Project     = "Harness"
  }
}

# Auto scaling configuration
resource "aws_apprunner_auto_scaling_configuration_version" "api" {
  auto_scaling_configuration_name = "${var.project_name}-api-autoscaling-${var.environment}"
  
  max_concurrency = 100
  max_size        = 10
  min_size        = 1

  tags = {
    Name        = "${var.project_name}-api-autoscaling-${var.environment}"
    Environment = var.environment
  }
}

# VPC Connector for database access
resource "aws_apprunner_vpc_connector" "main" {
  vpc_connector_name = "${var.project_name}-vpc-connector-${var.environment}"
  subnets            = aws_subnet.private[*].id
  security_groups    = [aws_security_group.apprunner.id]

  tags = {
    Name        = "${var.project_name}-vpc-connector-${var.environment}"
    Environment = var.environment
  }
}

# Security group for App Runner
resource "aws_security_group" "apprunner" {
  name_prefix = "${var.project_name}-apprunner-${var.environment}"
  vpc_id      = aws_vpc.harness.id

  # Outbound to database
  egress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.harness.cidr_block]
  }

  # Outbound to Redis
  egress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.harness.cidr_block]
  }

  # Outbound to Weaviate
  egress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.harness.cidr_block]
  }

  # Outbound HTTPS for external APIs
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Outbound HTTP for external APIs
  egress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-apprunner-sg-${var.environment}"
    Environment = var.environment
  }
}

# IAM role for App Runner instance
resource "aws_iam_role" "apprunner_instance" {
  name = "${var.project_name}-apprunner-instance-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "tasks.apprunner.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.project_name}-apprunner-instance-role-${var.environment}"
    Environment = var.environment
  }
}

# IAM policy for App Runner instance (S3, etc.)
resource "aws_iam_role_policy" "apprunner_instance" {
  name = "${var.project_name}-apprunner-instance-policy-${var.environment}"
  role = aws_iam_role.apprunner_instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.veterinary_corpus.arn,
          "${aws_s3_bucket.veterinary_corpus.arn}/*",
          aws_s3_bucket.embeddings.arn,
          "${aws_s3_bucket.embeddings.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:*:*"
      }
    ]
  })
}

# Custom domain configuration
resource "aws_apprunner_custom_domain_association" "api" {
  domain_name = "api.${var.domain_name}"
  service_arn = aws_apprunner_service.api.arn
}

# Route 53 record for custom domain
resource "aws_route53_record" "api_apprunner" {
  zone_id = aws_route53_zone.harness.zone_id
  name    = "api.${var.domain_name}"
  type    = "CNAME"
  ttl     = 300
  records = [aws_apprunner_custom_domain_association.api.dns_target]
}

# Outputs
output "apprunner_service_url" {
  description = "App Runner service URL"
  value       = aws_apprunner_service.api.service_url
}

output "apprunner_service_id" {
  description = "App Runner service ID"
  value       = aws_apprunner_service.api.service_id
}

output "apprunner_custom_domain" {
  description = "App Runner custom domain"
  value       = aws_apprunner_custom_domain_association.api.domain_name
}