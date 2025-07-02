# S3 Buckets for Veterinary Corpus and Model Storage

# Main corpus bucket for storing veterinary papers
resource "aws_s3_bucket" "veterinary_corpus" {
  bucket = "${var.project_name}-veterinary-corpus-${var.environment}"

  tags = {
    Name        = "${var.project_name}-veterinary-corpus-${var.environment}"
    Description = "Storage for veterinary papers PDFs and processed documents"
  }
}

# Enable versioning for corpus bucket
resource "aws_s3_bucket_versioning" "veterinary_corpus" {
  bucket = aws_s3_bucket.veterinary_corpus.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Lifecycle policy for corpus bucket
resource "aws_s3_bucket_lifecycle_configuration" "veterinary_corpus" {
  bucket = aws_s3_bucket.veterinary_corpus.id

  rule {
    id     = "archive-old-papers"
    status = "Enabled"

    filter {
      prefix = ""
    }

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 180
      storage_class = "GLACIER"
    }
  }
}

# Model artifacts bucket
resource "aws_s3_bucket" "model_artifacts" {
  bucket = "${var.project_name}-model-artifacts-${var.environment}"

  tags = {
    Name        = "${var.project_name}-model-artifacts-${var.environment}"
    Description = "Storage for MedGemma finetuned models and checkpoints"
  }
}

# Enable versioning for model artifacts
resource "aws_s3_bucket_versioning" "model_artifacts" {
  bucket = aws_s3_bucket.model_artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Training data bucket
resource "aws_s3_bucket" "training_data" {
  bucket = "${var.project_name}-training-data-${var.environment}"

  tags = {
    Name        = "${var.project_name}-training-data-${var.environment}"
    Description = "Processed training data for MedGemma finetuning"
  }
}

# Airflow logs bucket
resource "aws_s3_bucket" "airflow_logs" {
  bucket = "${var.project_name}-airflow-logs-${var.environment}"

  tags = {
    Name        = "${var.project_name}-airflow-logs-${var.environment}"
    Description = "Logs from Airflow data pipeline"
  }
}

# Lifecycle policy for logs
resource "aws_s3_bucket_lifecycle_configuration" "airflow_logs" {
  bucket = aws_s3_bucket.airflow_logs.id

  rule {
    id     = "delete-old-logs"
    status = "Enabled"

    filter {
      prefix = ""
    }

    expiration {
      days = 30
    }
  }
}

# S3 bucket for embeddings and vector data
resource "aws_s3_bucket" "embeddings" {
  bucket = "${var.project_name}-embeddings-${var.environment}"

  tags = {
    Name        = "${var.project_name}-embeddings-${var.environment}"
    Description = "Document embeddings and vector representations"
  }
}

# S3 VPC Endpoint for private access
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.harness.id
  service_name = "com.amazonaws.${var.aws_region}.s3"

  tags = {
    Name = "${var.project_name}-s3-endpoint-${var.environment}"
  }
}

# S3 bucket policies
resource "aws_s3_bucket_public_access_block" "veterinary_corpus" {
  bucket = aws_s3_bucket.veterinary_corpus.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "model_artifacts" {
  bucket = aws_s3_bucket.model_artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "training_data" {
  bucket = aws_s3_bucket.training_data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Output bucket names
output "veterinary_corpus_bucket" {
  value = aws_s3_bucket.veterinary_corpus.id
}

output "model_artifacts_bucket" {
  value = aws_s3_bucket.model_artifacts.id
}

output "training_data_bucket" {
  value = aws_s3_bucket.training_data.id
}