output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.harness.id
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = aws_subnet.private[*].id
}

output "s3_buckets" {
  description = "S3 bucket names"
  value = {
    veterinary_corpus = aws_s3_bucket.veterinary_corpus.id
    model_artifacts   = aws_s3_bucket.model_artifacts.id
    training_data     = aws_s3_bucket.training_data.id
    embeddings        = aws_s3_bucket.embeddings.id
    airflow_logs      = aws_s3_bucket.airflow_logs.id
  }
}

output "airflow_db_endpoint" {
  description = "Airflow RDS endpoint"
  value       = aws_db_instance.airflow.endpoint
  sensitive   = true
}

output "document_processing_queue_url" {
  description = "SQS queue URL for document processing"
  value       = aws_sqs_queue.document_processing.url
}

output "ecr_repository_url" {
  description = "ECR repository URL for training containers"
  value       = aws_ecr_repository.training.repository_url
}

output "sagemaker_domain_id" {
  description = "SageMaker domain ID"
  value       = aws_sagemaker_domain.harness.id
}

# Admin Frontend Infrastructure
output "admin_frontend_bucket" {
  description = "S3 bucket name for admin frontend"
  value       = aws_s3_bucket.admin_frontend.bucket
}

output "admin_cloudfront_distribution_id" {
  description = "CloudFront distribution ID for admin frontend"
  value       = aws_cloudfront_distribution.admin_frontend.id
}

output "admin_frontend_url" {
  description = "Admin frontend URL"
  value       = "https://admin.harness.health"
}

output "gpu_launch_template_id" {
  description = "GPU training launch template ID"
  value       = aws_launch_template.gpu_training.id
}