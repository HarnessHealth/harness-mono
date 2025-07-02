# Cost Management Setup for Harness

This document explains how to set up and use the AWS cost tracking features in Harness.

## Overview

Harness includes comprehensive AWS cost tracking to monitor and control your infrastructure expenses:

- Real-time cost tracking with AWS Cost Explorer integration
- Budget alerts and anomaly detection
- Service-level cost breakdown
- Monthly trends and projections
- Cost allocation by tags

## Configuration

### 1. Environment Variables

Set the following in your `.env` file:

```bash
# Set to "production" to use real AWS Cost Explorer API
AWS_ENVIRONMENT=production

# AWS credentials (if not using IAM roles)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1
```

### 2. AWS Permissions

The IAM role or user needs the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetCostForecast",
        "ce:GetReservationUtilization",
        "ce:GetDimensionValues",
        "ce:GetTags",
        "ce:GetAnomalies",
        "ce:GetAnomalyMonitors",
        "ce:GetAnomalySubscriptions",
        "budgets:ViewBudget",
        "budgets:DescribeBudget",
        "budgets:DescribeBudgetPerformanceHistory"
      ],
      "Resource": "*"
    }
  ]
}
```

### 3. Tagging Strategy

Ensure all AWS resources are tagged with:

```
Key: Project
Value: Harness
```

This allows the Cost Explorer to filter costs specific to the Harness project.

### 4. Cost Categories

The system automatically categorizes costs into:

- **Compute**: EC2, ECS, Lambda
- **Storage**: S3, EBS
- **Database**: RDS, ElastiCache
- **ML**: SageMaker, Bedrock
- **Other**: Route53, CloudFront, etc.

## Features

### Daily Cost Tracking

Monitor daily spending patterns with visual charts showing:
- Daily cost trends
- Weekend vs weekday patterns
- Cost spikes and anomalies

### Service Breakdown

View costs broken down by AWS service:
- EC2 instances for compute
- S3 for storage
- RDS for databases
- SageMaker for ML training
- CloudFront for CDN

### Budget Management

- Monthly budget: $5,000 (configurable)
- Email alerts at 80%, 100%, and 120% utilization
- Separate budgets for high-cost services like SageMaker

### Anomaly Detection

Automatic detection of unusual cost spikes:
- Daily monitoring for cost anomalies
- Email notifications for significant deviations
- Root cause analysis in the admin dashboard

### Monthly Trends

Track long-term cost patterns:
- 6-month historical trends
- Category-wise cost evolution
- Seasonal patterns identification

## Using the Cost Dashboard

1. Navigate to the Costs page in the admin frontend
2. Select time range: 7 days, 30 days, or 90 days
3. View different tabs:
   - **Overview**: Current month summary and projections
   - **Services**: Detailed service-level breakdown
   - **Trends**: Historical monthly trends

## Development Mode

When `AWS_ENVIRONMENT` is not set to "production", the system uses realistic demo data:
- Simulated daily costs with weekly patterns
- Mock service breakdowns
- Sample anomalies for testing

## Troubleshooting

### Cost data not showing

1. Check AWS credentials in `.env`
2. Verify IAM permissions
3. Ensure Cost Explorer is enabled in AWS Console
4. Check that resources are properly tagged

### High costs detected

1. Review the anomaly alerts
2. Check service breakdown for unexpected usage
3. Review recent deployments or training jobs
4. Set up additional budget alerts if needed

## Terraform Resources

The infrastructure includes:

- Cost categories for automatic grouping
- Monthly and service-specific budgets
- Anomaly monitors and subscriptions
- IAM policies for Cost Explorer access

Run `terraform apply` in the infrastructure directory to create these resources.

## Best Practices

1. **Tag Everything**: Ensure all resources are tagged with Project=Harness
2. **Regular Reviews**: Check the cost dashboard weekly
3. **Act on Anomalies**: Investigate cost spikes immediately
4. **Optimize Resources**: Use the data to right-size instances
5. **Set Budgets**: Configure budgets for each major service

## API Endpoints

- `GET /api/v1/admin/costs?time_range=30d` - Get cost data
- Time ranges: `7d`, `30d`, `90d`

## Frontend Integration

The costs page automatically fetches data from the API and displays:
- Real-time cost information
- Interactive charts using Recharts
- Responsive design for mobile viewing
- Auto-refresh every 5 minutes