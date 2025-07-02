# Harness Deployment Guide

This guide walks through deploying the Harness veterinary AI platform infrastructure and services.

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **Tools installed**:
   - AWS CLI (configured with credentials)
   - Terraform >= 1.5.0
   - Docker
   - Python 3.12+
   - jq (for JSON processing)

3. **Environment variables** in `.env.local`:
   - AWS_ACCESS_KEY_ID
   - AWS_SECRET_ACCESS_KEY
   - AWS_REGION (default: us-east-1)

## Quick Deployment

```bash
# 1. Deploy all infrastructure
./scripts/deployment/deploy.sh

# 2. Start data acquisition
# This happens automatically via Airflow DAGs

# 3. Start model training (when ready)
./scripts/deployment/start_training.sh start

# 4. Run evaluation
./scripts/deployment/run_evaluation.sh run <model_path>
```

## Step-by-Step Deployment

### 1. Infrastructure Deployment

Deploy the AWS infrastructure using Terraform:

```bash
cd infrastructure/terraform

# Initialize Terraform
terraform init

# Review planned changes
terraform plan

# Apply infrastructure
terraform apply
```

This creates:
- VPC with public/private subnets
- S3 buckets for corpus, models, and training data
- RDS for Airflow metadata
- ECS cluster for Airflow
- Lambda functions for document processing
- GPU instance templates for training

### 2. Build and Push Docker Images

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ECR_URL>

# Build and push backend
docker build -f infrastructure/docker/Dockerfile.backend -t harness-backend .
docker tag harness-backend:latest <ECR_URL>:backend-latest
docker push <ECR_URL>:backend-latest

# Build and push Lambda
cd data-pipeline/lambdas/grobid_processor
docker build -t harness-grobid-processor .
docker tag harness-grobid-processor:latest <ECR_URL>:grobid-processor-latest
docker push <ECR_URL>:grobid-processor-latest
```

### 3. Deploy Airflow

1. **Deploy Airflow on ECS**:
   ```bash
   # Use the ECS task definition
   aws ecs create-service \
     --cluster harness-airflow-development \
     --service-name airflow-webserver \
     --task-definition harness-airflow-webserver
   ```

2. **Upload DAGs to S3**:
   ```bash
   aws s3 sync data-pipeline/dags/ s3://harness-airflow-logs-development/dags/
   ```

3. **Configure Airflow connections**:
   - PubMed API
   - Europe PMC API
   - Unpaywall (requires email)
   - AWS (for S3 access)

### 4. Start Data Acquisition

The data pipeline runs automatically via Airflow DAGs:

1. **Daily corpus acquisition**: Crawls PubMed, Europe PMC, conferences
2. **Document processing**: GROBID extraction via Lambda
3. **Embedding generation**: Creates vector representations
4. **Index updates**: Updates Weaviate vector database

Monitor progress in Airflow UI or CloudWatch logs.

### 5. Prepare Training Data

Before training MedGemma:

1. **Create training datasets**:
   ```python
   # Upload to S3
   aws s3 cp veterinary_qa_dataset.jsonl \
     s3://harness-training-data-development/datasets/veterinary_qa_v1/
   ```

2. **Verify data quality**:
   - Check citation accuracy
   - Validate question-answer pairs
   - Ensure species diversity

### 6. Fine-tune MedGemma

1. **Launch GPU instance**:
   ```bash
   ./scripts/deployment/start_training.sh start
   ```

2. **Monitor training**:
   - Weights & Biases dashboard
   - CloudWatch logs
   - GPU utilization metrics

3. **Training phases**:
   - Phase 1: Domain adaptation (2 weeks)
   - Phase 2: Instruction tuning (3 weeks)
   - Phase 3: Safety alignment (1 week)
   - Phase 4: Citation training (1 week)

### 7. Evaluate Models

After training completes:

```bash
# List available models
./scripts/deployment/run_evaluation.sh list

# Run evaluation
./scripts/deployment/run_evaluation.sh run s3://harness-model-artifacts/final_models/medgemma-27b-vet-it-v1

# Compare models
./scripts/deployment/run_evaluation.sh compare

# Generate report
./scripts/deployment/run_evaluation.sh report s3://harness-model-artifacts/evaluation_results/<job_name>
```

### 8. Deploy API Services

Once models are trained and evaluated:

```bash
# Update model endpoint in configuration
vim backend/api/config.py  # Update INFERENCE_ENDPOINT

# Deploy API on ECS/EKS
kubectl apply -f infrastructure/kubernetes/
```

## Cost Optimization

1. **Use Spot Instances** for training (90% cost savings)
2. **Stop instances** when not in use:
   ```bash
   ./scripts/deployment/start_training.sh stop
   ```
3. **S3 Lifecycle policies** automatically archive old data
4. **Reserved Instances** for production inference

## Monitoring

### Dashboards
- **CloudWatch**: Infrastructure metrics
- **Weights & Biases**: Training metrics
- **Grafana**: Application metrics

### Alerts
- Training job failures
- High inference latency
- Low citation accuracy
- Safety score drops

## Troubleshooting

### Common Issues

1. **GROBID Lambda timeout**:
   - Increase Lambda timeout (max 15 min)
   - Use batch processing for large PDFs

2. **GPU OOM during training**:
   - Reduce batch size
   - Enable gradient checkpointing
   - Use larger instance type

3. **Slow data acquisition**:
   - Check API rate limits
   - Increase Airflow worker count
   - Optimize crawling patterns

### Debug Commands

```bash
# Check Airflow logs
aws logs tail /ecs/harness-airflow --follow

# SSH to GPU instance
aws ssm start-session --target <instance-id>

# Check training logs
aws s3 cp s3://harness-model-artifacts/logs/training.log -

# Verify S3 permissions
aws s3 ls s3://harness-veterinary-corpus-development/
```

## Security Considerations

1. **Rotate credentials** regularly
2. **Enable MFA** for AWS accounts
3. **Use VPC endpoints** for S3 access
4. **Encrypt data** at rest and in transit
5. **Audit logs** with CloudTrail

## Backup and Recovery

1. **Database backups**: RDS automated backups (7-day retention)
2. **Model checkpoints**: S3 versioning enabled
3. **Corpus data**: S3 cross-region replication
4. **Configuration**: Store in version control

## Production Checklist

- [ ] SSL certificates configured
- [ ] Domain names set up
- [ ] Auto-scaling configured
- [ ] Monitoring alerts enabled
- [ ] Backup strategy tested
- [ ] Security audit completed
- [ ] Load testing performed
- [ ] Documentation updated