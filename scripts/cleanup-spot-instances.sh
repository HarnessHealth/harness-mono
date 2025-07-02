#!/bin/bash
# Cleanup script for spot instances to free up quota

set -e

AWS_REGION=${AWS_REGION:-us-east-1}
AWS_PROFILE=${AWS_PROFILE:-default}

echo "🧹 Spot Instance Cleanup Tool"
echo "=========================="
echo "AWS Region: $AWS_REGION"
echo ""

# Check current spot instance requests
echo "Checking active spot instance requests..."
SPOT_REQUESTS=$(aws ec2 describe-spot-instance-requests \
    --filters "Name=state,Values=active,open" \
    --query 'SpotInstanceRequests[*].[SpotInstanceRequestId,InstanceId,State,InstanceType]' \
    --output table \
    --profile $AWS_PROFILE \
    --region $AWS_REGION)

if [[ -n "$SPOT_REQUESTS" && "$SPOT_REQUESTS" != *"None"* ]]; then
    echo "Active spot requests found:"
    echo "$SPOT_REQUESTS"
    echo ""
    
    # Get spot request IDs
    SPOT_REQUEST_IDS=$(aws ec2 describe-spot-instance-requests \
        --filters "Name=state,Values=active,open" \
        --query 'SpotInstanceRequests[*].SpotInstanceRequestId' \
        --output text \
        --profile $AWS_PROFILE \
        --region $AWS_REGION)
    
    if [[ -n "$SPOT_REQUEST_IDS" && "$SPOT_REQUEST_IDS" != "None" ]]; then
        echo "❓ Cancel these spot requests? (y/N)"
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            echo "Canceling spot requests..."
            aws ec2 cancel-spot-instance-requests \
                --spot-instance-request-ids $SPOT_REQUEST_IDS \
                --profile $AWS_PROFILE \
                --region $AWS_REGION
            echo "✅ Spot requests canceled"
        fi
    fi
else
    echo "✅ No active spot requests found"
fi

# Check running spot instances
echo ""
echo "Checking running spot instances..."
SPOT_INSTANCES=$(aws ec2 describe-instances \
    --filters "Name=instance-lifecycle,Values=spot" \
           "Name=instance-state-name,Values=running,pending" \
    --query 'Reservations[*].Instances[*].[InstanceId,InstanceType,State.Name,Tags[?Key==`Name`].Value|[0]]' \
    --output table \
    --profile $AWS_PROFILE \
    --region $AWS_REGION)

if [[ -n "$SPOT_INSTANCES" && "$SPOT_INSTANCES" != *"None"* ]]; then
    echo "Running spot instances found:"
    echo "$SPOT_INSTANCES"
    echo ""
    
    # Get instance IDs
    SPOT_INSTANCE_IDS=$(aws ec2 describe-instances \
        --filters "Name=instance-lifecycle,Values=spot" \
               "Name=instance-state-name,Values=running,pending" \
        --query 'Reservations[*].Instances[*].InstanceId' \
        --output text \
        --profile $AWS_PROFILE \
        --region $AWS_REGION)
    
    if [[ -n "$SPOT_INSTANCE_IDS" && "$SPOT_INSTANCE_IDS" != "None" ]]; then
        echo "❓ Terminate these spot instances? (y/N)"
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            echo "Terminating spot instances..."
            aws ec2 terminate-instances \
                --instance-ids $SPOT_INSTANCE_IDS \
                --profile $AWS_PROFILE \
                --region $AWS_REGION
            echo "✅ Spot instances terminated"
        fi
    fi
else
    echo "✅ No running spot instances found"
fi

# Show current quota usage
echo ""
echo "📊 Current EC2 Quota Usage:"
echo "=========================="

# Count running instances
RUNNING_COUNT=$(aws ec2 describe-instances \
    --filters "Name=instance-state-name,Values=running,pending" \
    --query 'Reservations[*].Instances[*].InstanceId' \
    --output text \
    --profile $AWS_PROFILE \
    --region $AWS_REGION | wc -w)

echo "Running instances: $RUNNING_COUNT/20"

# Count spot instances specifically  
SPOT_COUNT=$(aws ec2 describe-instances \
    --filters "Name=instance-lifecycle,Values=spot" \
           "Name=instance-state-name,Values=running,pending" \
    --query 'Reservations[*].Instances[*].InstanceId' \
    --output text \
    --profile $AWS_PROFILE \
    --region $AWS_REGION | wc -w)

echo "Spot instances: $SPOT_COUNT"

echo ""
echo "💡 Solutions for MaxSpotInstanceCountExceeded:"
echo "1. Run this script to clean up unused spot instances"
echo "2. Use on-demand instances (automatic fallback in training script)"
echo "3. Request spot instance quota increase:"
echo "   👉 https://console.aws.amazon.com/servicequotas/home/services/ec2/quotas"
echo "4. Use SageMaker for managed training (no spot limits)"

echo ""
echo "🚀 Ready to launch training again!"