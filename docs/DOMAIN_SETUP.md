# Setting up harness.health Domain

This guide will help you configure your harness.health domain to point to your AWS infrastructure.

## Prerequisites

1. Domain Registration: Ensure you own the harness.health domain
2. AWS Account with appropriate permissions
3. Terraform installed locally
4. AWS CLI configured

## Step 1: Deploy AWS Infrastructure

First, deploy the infrastructure using Terraform:

```bash
cd infrastructure/terraform
terraform init
terraform plan
terraform apply
```

This will create:
- Route53 hosted zone for harness.health
- SSL/TLS certificate via AWS Certificate Manager
- Application Load Balancer with HTTPS
- ECS cluster and services for API and Admin
- RDS PostgreSQL database
- ElastiCache Redis
- All necessary security groups and networking

## Step 2: Configure Domain Nameservers

After Terraform completes, you'll see output with nameservers:

```
nameservers = [
  "ns-xxx.awsdns-xx.com",
  "ns-xxx.awsdns-xx.net",
  "ns-xxx.awsdns-xx.org",
  "ns-xxx.awsdns-xx.co.uk"
]
```

Go to your domain registrar (where you purchased harness.health) and update the nameservers to these AWS Route53 nameservers.

## Step 3: Build and Deploy Docker Images

### API Backend
```bash
# Build API Docker image
cd backend
docker build -f ../infrastructure/docker/Dockerfile.backend -t harness-api .

# Tag and push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <your-account-id>.dkr.ecr.us-east-1.amazonaws.com
docker tag harness-api:latest <your-account-id>.dkr.ecr.us-east-1.amazonaws.com/harness/api:latest
docker push <your-account-id>.dkr.ecr.us-east-1.amazonaws.com/harness/api:latest
```

### Admin Frontend
```bash
# Build Admin Frontend Docker image
cd admin-frontend
docker build -f Dockerfile -t harness-admin .

# Tag and push to ECR
docker tag harness-admin:latest <your-account-id>.dkr.ecr.us-east-1.amazonaws.com/harness/admin:latest
docker push <your-account-id>.dkr.ecr.us-east-1.amazonaws.com/harness/admin:latest
```

## Step 4: Update ECS Services

After pushing images, update the ECS services:

```bash
# Force new deployment to pull latest images
aws ecs update-service --cluster harness-main-production --service harness-api-production --force-new-deployment
aws ecs update-service --cluster harness-main-production --service harness-admin-production --force-new-deployment
```

## Step 5: Verify DNS Resolution

After nameserver propagation (can take 24-48 hours), verify DNS:

```bash
# Check DNS resolution
nslookup harness.health
nslookup api.harness.health
nslookup admin.harness.health

# Test HTTPS endpoints
curl -I https://harness.health
curl -I https://api.harness.health/api/health
curl -I https://admin.harness.health
```

## URLs After Setup

- Main site: https://harness.health
- API: https://api.harness.health
- Admin Dashboard: https://admin.harness.health
- API Documentation: https://api.harness.health/api/docs

## Troubleshooting

### DNS Not Resolving
- Ensure nameservers are correctly set at your registrar
- Wait for DNS propagation (up to 48 hours)
- Check Route53 hosted zone is active

### Certificate Validation Failed
- Check Route53 has the ACM validation records
- Ensure domain ownership is verified

### Services Not Accessible
- Check ECS services are running: `aws ecs list-services --cluster harness-main-production`
- Check ALB target groups are healthy in AWS Console
- Review CloudWatch logs for errors

### Database Connection Issues
- Ensure security groups allow traffic from ECS tasks
- Verify RDS is in the same VPC as ECS
- Check database credentials in ECS task definition

## Security Considerations

1. **HTTPS Only**: All HTTP traffic is redirected to HTTPS
2. **Security Groups**: Restrictive security groups limit access
3. **Private Subnets**: Database and cache are in private subnets
4. **Secrets**: Database passwords are generated randomly by Terraform
5. **SSL/TLS**: Using modern TLS 1.3 policy on ALB

## Next Steps

1. Set up CloudFront CDN for better global performance
2. Configure WAF rules for additional security
3. Set up monitoring and alerts in CloudWatch
4. Configure auto-scaling for ECS services
5. Set up CI/CD pipeline for automated deployments