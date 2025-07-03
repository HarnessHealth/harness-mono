# Simplified App Runner configuration for reference
# Note: We're using deployment scripts instead of Terraform for App Runner services
# This file is kept for reference and future infrastructure-as-code needs

# IAM role for App Runner instance (for S3 access)
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

# IAM policy for App Runner instance (S3 access for document storage)
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

# Output the role ARN for use in deployment scripts
output "apprunner_instance_role_arn" {
  description = "ARN of the App Runner instance role"
  value       = aws_iam_role.apprunner_instance.arn
}