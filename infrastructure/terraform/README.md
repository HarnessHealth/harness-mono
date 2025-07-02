# Harness AWS Infrastructure

This directory contains Terraform configurations for deploying the Harness veterinary AI platform infrastructure on AWS.

## Infrastructure Components

### Networking
- VPC with public and private subnets across 3 availability zones
- NAT Gateways for private subnet internet access
- Security groups for various services

### Storage (S3 Buckets)
- **veterinary-corpus**: Raw veterinary papers and PDFs
- **model-artifacts**: Fine-tuned MedGemma models and checkpoints
- **training-data**: Processed training datasets
- **embeddings**: Document embeddings for vector search
- **airflow-logs**: Pipeline execution logs

### Data Pipeline
- ECS cluster for Airflow
- RDS PostgreSQL for Airflow metadata
- SQS queues for document processing
- Lambda functions for GROBID processing

### ML Training Infrastructure
- EC2 launch templates for GPU instances (p4d.24xlarge - 8x A100)
- Auto Scaling Groups with Spot instance support
- SageMaker domain for managed training
- ECR repository for training containers

## Prerequisites

1. AWS CLI configured with credentials
2. Terraform >= 1.5.0
3. Existing S3 bucket for Terraform state (update in `main.tf`)

## Usage

### 1. Initialize Terraform
```bash
terraform init
```

### 2. Create terraform.tfvars
```hcl
aws_region = "us-east-1"
environment = "development"
project_name = "harness"
```

### 3. Plan Infrastructure
```bash
terraform plan
```

### 4. Apply Infrastructure
```bash
terraform apply
```

## Cost Optimization

### GPU Training
- Uses Spot instances by default (up to 90% cost savings)
- Auto Scaling Group scales to 0 when not in use
- Mixed instance policy allows p4d.24xlarge or p3dn.24xlarge

### Storage
- S3 lifecycle policies move old data to cheaper storage tiers
- Intelligent-Tiering for corpus bucket
- Log retention policies to prevent unlimited growth

### Compute
- Use of managed services (Lambda, SQS) for serverless processing
- ECS with Fargate Spot for Airflow workers

## Security

- All S3 buckets have encryption enabled
- VPC endpoints for private S3 access
- Security groups follow principle of least privilege
- IAM roles with minimal required permissions

## Monitoring

- CloudWatch Logs for all services
- Container Insights enabled for ECS
- VPC Flow Logs available if needed

## Destroying Infrastructure

To tear down all resources:
```bash
terraform destroy
```

**Warning**: This will delete all resources including S3 buckets and their contents.