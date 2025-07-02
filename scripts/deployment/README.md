# Harness Deployment Scripts

This directory contains deployment scripts for the Harness infrastructure and applications.

## Main Deploy Script

### Usage

```bash
# Deploy entire infrastructure
./deploy.sh

# Deploy only admin frontend
./deploy.sh --admin-frontend
# or
./deploy.sh --admin

# Deploy only backend services
./deploy.sh --backend

# Show help
./deploy.sh --help
```

### Environment Variables

- `ENVIRONMENT`: Deployment environment (default: development)
- `AWS_REGION`: AWS region (default: us-east-1)
- `AWS_PROFILE`: AWS CLI profile (default: default)

### Examples

```bash
# Deploy to production
ENVIRONMENT=production ./deploy.sh

# Deploy admin frontend to production using specific AWS profile
ENVIRONMENT=production AWS_PROFILE=harness-prod ./deploy.sh --admin-frontend

# Deploy backend services to staging
ENVIRONMENT=staging ./deploy.sh --backend
```

## Admin Frontend Quick Deploy

For convenience, there's also a dedicated deploy script in the admin-frontend directory:

```bash
cd admin-frontend
./deploy.sh
```

This script:
- Builds the React application
- Uploads to S3
- Sets proper cache headers
- Invalidates CloudFront cache
- Works independently of Terraform state

## Prerequisites

All deployment scripts require:

1. **AWS CLI** - [Install guide](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-install.html)
2. **Terraform** - [Install guide](https://learn.hashicorp.com/tutorials/terraform/install-cli) (for full deployment)
3. **Docker** - [Install guide](https://docs.docker.com/get-docker/) (for backend deployment)
4. **Node.js & npm** - [Install guide](https://nodejs.org/) (for frontend deployment)
5. **jq** - JSON processor (optional but recommended)

## Deployment Process

### Full Infrastructure Deployment

1. Creates Terraform backend S3 bucket
2. Deploys AWS infrastructure with Terraform
3. Builds and pushes Docker images to ECR
4. Deploys Lambda functions
5. Sets up Airflow
6. Creates S3 bucket structure
7. Uploads scripts
8. Deploys admin frontend

### Admin Frontend Only

1. Builds the React application
2. Uploads built files to S3
3. Sets appropriate cache headers
4. Invalidates CloudFront distribution

### Backend Services Only

1. Builds Docker images
2. Pushes to ECR
3. Updates Lambda functions
4. Updates ECS services

## Infrastructure Outputs

After deployment, important endpoints are displayed:

- Admin Frontend URL: https://admin.harness.health
- API Endpoint: https://api.harness.health
- Airflow URL: (internal)
- RDS Endpoint: (internal)

## Troubleshooting

### S3 Bucket Not Found

If the admin frontend deployment can't find the S3 bucket:

1. Ensure infrastructure is deployed first
2. Check Terraform outputs: `terraform output -json`
3. Verify AWS credentials and region

### Docker Build Failures

1. Ensure Docker daemon is running
2. Check available disk space
3. Verify ECR repository exists

### CloudFront Invalidation

CloudFront invalidations can take 5-10 minutes to complete. Check status:

```bash
aws cloudfront get-invalidation \
  --distribution-id YOUR_DISTRIBUTION_ID \
  --id YOUR_INVALIDATION_ID
```

## Security Notes

- Never commit AWS credentials
- Use IAM roles when possible
- Restrict S3 bucket policies
- Enable CloudFront security headers
- Use HTTPS for all endpoints

## Cost Optimization

- Admin frontend uses CloudFront for global distribution
- S3 lifecycle policies remove old builds
- Backend uses auto-scaling for cost efficiency
- Lambda functions are pay-per-use

## Monitoring

After deployment, monitor:

- CloudFront metrics in AWS Console
- S3 bucket access logs
- ECS service health
- Lambda function logs
- Application logs in CloudWatch