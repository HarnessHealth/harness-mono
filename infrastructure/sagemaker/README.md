# MedGemma SageMaker Deployment

This directory contains scripts and configurations for deploying Google's MedGemma models to Amazon SageMaker.

## Available Models

- **MedGemma-4B-IT**: Smaller model, good for development and testing
  - Cost: ~$1.01/hour (ml.g5.2xlarge)
  - Memory: 32GB RAM, 1 GPU
  
- **MedGemma-7B-IT**: Medium model, balanced performance and cost
  - Cost: ~$1.69/hour (ml.g5.4xlarge)
  - Memory: 64GB RAM, 1 GPU
  
- **MedGemma-27B-IT**: Large model, best performance
  - Cost: ~$5.67/hour (ml.g5.12xlarge)
  - Memory: 192GB RAM, 4 GPUs

## Quick Deployment

### Prerequisites

1. AWS credentials configured
2. SageMaker execution role with proper permissions
3. HuggingFace access token (should be in environment variables)

### Deploy MedGemma-27B-IT (Recommended)

```bash
# Quick deployment
make deploy-medgemma

# Or run directly
python deploy_medgemma_now.py
```

### Deploy Other Sizes

```bash
# 4B model (cheaper for testing)
make deploy-medgemma-4b

# 7B model (medium size)
make deploy-medgemma-7b
```

### Advanced Deployment

```bash
# Deploy with custom configuration
python infrastructure/sagemaker/deploy_medgemma.py --model-size 27b --environment production
```

## Infrastructure Setup

If you need to set up the SageMaker infrastructure first:

```bash
# Set up IAM roles and S3 buckets
make sagemaker-setup

# Or manually with Terraform
cd infrastructure/terraform
terraform apply -target=aws_iam_role.sagemaker_execution_role
```

## Cost Estimation

| Model | Instance Type | Hourly Cost | Daily Cost (8h) | Monthly Cost |
|-------|---------------|-------------|-----------------|--------------|
| 4B    | ml.g5.2xlarge | $1.01       | $8.08          | $242         |
| 7B    | ml.g5.4xlarge | $1.69       | $13.52         | $406         |
| 27B   | ml.g5.12xlarge| $5.67       | $45.36         | $1,361       |

## Usage Example

Once deployed, you can use the endpoint like this:

```python
import boto3
import json

# Initialize SageMaker runtime
runtime = boto3.client('sagemaker-runtime')

# Prepare the payload
payload = {
    "inputs": "What are the symptoms of canine parvovirus?",
    "parameters": {
        "max_new_tokens": 200,
        "temperature": 0.7,
        "do_sample": True
    }
}

# Call the endpoint
response = runtime.invoke_endpoint(
    EndpointName='medgemma-27b-it-20240703-123456',
    ContentType='application/json',
    Body=json.dumps(payload)
)

# Parse response
result = json.loads(response['Body'].read().decode())
print(result[0]['generated_text'])
```

## Monitoring and Management

### View Endpoints
```bash
aws sagemaker list-endpoints
```

### Check Endpoint Status
```bash
aws sagemaker describe-endpoint --endpoint-name your-endpoint-name
```

### Delete Endpoint
```bash
aws sagemaker delete-endpoint --endpoint-name your-endpoint-name
```

### View CloudWatch Metrics
- Go to AWS Console > CloudWatch > Metrics > AWS/SageMaker
- Monitor: Invocations, ModelLatency, OverheadLatency

## Troubleshooting

### Common Issues

1. **Insufficient Service Quota**
   - Error: "ResourceLimitExceeded"
   - Solution: Request quota increase for the instance type in AWS Console

2. **SageMaker Role Not Found**
   - Error: "Role not found"
   - Solution: Run `make sagemaker-setup` to create the role

3. **HuggingFace Token Invalid**
   - Error: "Authentication failed"
   - Solution: Verify your HF token has access to the model

4. **Deployment Timeout**
   - Error: "Container failed to start"
   - Solution: Try a larger instance type or check CloudWatch logs

### Logs and Debugging

Check CloudWatch logs for detailed error messages:
```bash
aws logs describe-log-groups --log-group-name-prefix /aws/sagemaker/Endpoints
```

## Security Notes

- HuggingFace tokens should be stored securely (AWS Secrets Manager in production)
- SageMaker endpoints are private by default
- Enable VPC configuration for additional security
- Use IAM policies to restrict access to endpoints

## Integration with Harness Backend

The deployed endpoints can be integrated with the Harness inference service:

1. Update `backend/services/inference/config.py` with the endpoint name
2. Modify the inference client to use SageMaker runtime
3. Add proper error handling and retry logic
4. Implement request batching for efficiency

## Cost Optimization

1. **Auto-scaling**: Enable to scale down during low usage
2. **Scheduled scaling**: Turn off endpoints during non-business hours
3. **Multi-model endpoints**: Host multiple models on single endpoint
4. **Spot instances**: Use for non-critical workloads (when available)