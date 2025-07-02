# ECS Cluster for Airflow
resource "aws_ecs_cluster" "airflow" {
  name = "${var.project_name}-airflow-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.project_name}-airflow-${var.environment}"
  }
}

# RDS for Airflow Metadata
resource "aws_db_subnet_group" "airflow" {
  name       = "${var.project_name}-airflow-db-subnet-${var.environment}"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "${var.project_name}-airflow-db-subnet-${var.environment}"
  }
}

resource "aws_security_group" "airflow_db" {
  name        = "${var.project_name}-airflow-db-sg-${var.environment}"
  description = "Security group for Airflow RDS"
  vpc_id      = aws_vpc.harness.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.airflow.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-airflow-db-sg-${var.environment}"
  }
}

resource "aws_db_instance" "airflow" {
  identifier     = "${var.project_name}-airflow-db-${var.environment}"
  engine         = "postgres"
  engine_version = "15.13"
  instance_class = "db.t3.medium"
  
  allocated_storage     = 100
  storage_type         = "gp3"
  storage_encrypted    = true
  
  db_name  = "airflow"
  username = "airflow"
  password = random_password.airflow_db.result
  
  vpc_security_group_ids = [aws_security_group.airflow_db.id]
  db_subnet_group_name   = aws_db_subnet_group.airflow.name
  
  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "sun:04:00-sun:05:00"
  
  skip_final_snapshot = true
  deletion_protection = false

  tags = {
    Name = "${var.project_name}-airflow-db-${var.environment}"
  }
}

resource "random_password" "airflow_db" {
  length           = 32
  special          = true
  override_special = "!#$%&*()_+-=[]{}|;:,.<>?"
}

# SQS Queue for document processing
resource "aws_sqs_queue" "document_processing" {
  name                       = "${var.project_name}-document-processing-${var.environment}"
  delay_seconds              = 0
  max_message_size          = 262144
  message_retention_seconds  = 1209600 # 14 days
  receive_wait_time_seconds  = 10
  visibility_timeout_seconds = 300

  tags = {
    Name = "${var.project_name}-document-processing-${var.environment}"
  }
}

# DLQ for failed processing
resource "aws_sqs_queue" "document_processing_dlq" {
  name                      = "${var.project_name}-document-processing-dlq-${var.environment}"
  message_retention_seconds = 1209600 # 14 days

  tags = {
    Name = "${var.project_name}-document-processing-dlq-${var.environment}"
  }
}

# Lambda for GROBID processing
resource "aws_lambda_function" "grobid_processor" {
  function_name = "${var.project_name}-grobid-processor-${var.environment}"
  role          = aws_iam_role.grobid_lambda.arn
  
  # Placeholder - will be replaced with actual deployment package
  filename         = "grobid_processor.zip"
  source_code_hash = filebase64sha256("grobid_processor.zip")
  
  handler = "main.handler"
  runtime = "python3.12"
  timeout = 300
  memory_size = 3008

  environment {
    variables = {
      S3_CORPUS_BUCKET  = aws_s3_bucket.veterinary_corpus.id
      S3_TRAINING_BUCKET = aws_s3_bucket.training_data.id
      GROBID_ENDPOINT   = "http://grobid.${var.project_name}.internal:8070"
    }
  }

  # VPC config removed - Lambda needs internet access to crawl external APIs (PMC, PubMed)
  # vpc_config {
  #   subnet_ids         = aws_subnet.private[*].id
  #   security_group_ids = [aws_security_group.lambda.id]
  # }

  tags = {
    Name = "${var.project_name}-grobid-processor-${var.environment}"
  }
}

# Security group for Lambda
resource "aws_security_group" "lambda" {
  name        = "${var.project_name}-lambda-sg-${var.environment}"
  description = "Security group for Lambda functions"
  vpc_id      = aws_vpc.harness.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-lambda-sg-${var.environment}"
  }
}

# EventBridge for scheduled crawling
resource "aws_cloudwatch_event_rule" "daily_crawl" {
  name                = "${var.project_name}-daily-crawl-${var.environment}"
  description         = "Trigger daily veterinary paper crawling"
  schedule_expression = "cron(0 2 * * ? *)" # 2 AM UTC daily

  tags = {
    Name = "${var.project_name}-daily-crawl-${var.environment}"
  }
}

# IAM Role for Lambda
resource "aws_iam_role" "grobid_lambda" {
  name = "${var.project_name}-grobid-lambda-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-grobid-lambda-role-${var.environment}"
  }
}

# IAM Policy for Lambda
resource "aws_iam_role_policy" "grobid_lambda" {
  name = "${var.project_name}-grobid-lambda-policy-${var.environment}"
  role = aws_iam_role.grobid_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.veterinary_corpus.arn,
          "${aws_s3_bucket.veterinary_corpus.arn}/*",
          aws_s3_bucket.training_data.arn,
          "${aws_s3_bucket.training_data.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.document_processing.arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # VPC permissions removed - no longer needed without VPC config
      # {
      #   Effect = "Allow"
      #   Action = [
      #     "ec2:CreateNetworkInterface",
      #     "ec2:DescribeNetworkInterfaces",
      #     "ec2:DeleteNetworkInterface"
      #   ]
      #   Resource = "*"
      # }
    ]
  })
}