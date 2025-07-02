#!/bin/bash
# Harness Model Training Launch Script

set -e

# Configuration
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ENVIRONMENT=${ENVIRONMENT:-development}
AWS_REGION=${AWS_REGION:-us-east-1}
AWS_PROFILE=${AWS_PROFILE:-default}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Harness MedGemma Training Launcher${NC}"
echo "==================================="
echo "Environment: $ENVIRONMENT"
echo "AWS Region: $AWS_REGION"
echo ""

# Function to launch GPU training instance
launch_training_instance() {
    echo -e "${YELLOW}Launching GPU training instance...${NC}"
    
    # Get launch template ID from Terraform
    LAUNCH_TEMPLATE=$(terraform -chdir=infrastructure/terraform output -raw gpu_launch_template_id 2>/dev/null || echo "")
    
    if [ -z "$LAUNCH_TEMPLATE" ]; then
        echo -e "${RED}Launch template not found. Deploy infrastructure first.${NC}"
        exit 1
    fi
    
    # Get subnet IDs from supported AZs (avoid us-east-1a due to capacity issues)
    SUBNET_IDS=$(terraform -chdir=infrastructure/terraform output -json private_subnet_ids | jq -r '.[]' 2>/dev/null)
    
    # Find a subnet not in us-east-1a 
    SUBNET_ID=""
    for subnet in $SUBNET_IDS; do
        AZ=$(aws ec2 describe-subnets --subnet-ids $subnet --query 'Subnets[0].AvailabilityZone' --output text --profile $AWS_PROFILE --region $AWS_REGION 2>/dev/null)
        if [[ "$AZ" != "us-east-1a" ]]; then
            SUBNET_ID=$subnet
            echo "Selected subnet $SUBNET_ID in $AZ"
            break
        fi
    done
    
    if [ -z "$SUBNET_ID" ]; then
        echo -e "${RED}No suitable subnet found outside us-east-1a${NC}"
        exit 1
    fi
    
    # Launch instance with fallback to on-demand if spot fails
    echo "Attempting to launch spot instance..."
    
    INSTANCE_ID=$(aws ec2 run-instances \
        --launch-template LaunchTemplateId=$LAUNCH_TEMPLATE,Version=\$Latest \
        --subnet-id $SUBNET_ID \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=harness-training-$(date +%Y%m%d-%H%M%S)},{Key=Purpose,Value=medgemma-finetuning}]" \
        --query 'Instances[0].InstanceId' \
        --output text \
        --profile $AWS_PROFILE \
        --region $AWS_REGION 2>/dev/null) || {
        
        echo -e "${YELLOW}Spot instance launch failed. Attempting on-demand instance...${NC}"
        
        # Get launch template without spot pricing
        LAUNCH_TEMPLATE_ON_DEMAND=$(aws ec2 create-launch-template \
            --launch-template-name "harness-training-ondemand-$(date +%s)" \
            --launch-template-data '{
                "ImageId": "'$(aws ec2 describe-launch-template-versions --launch-template-id $LAUNCH_TEMPLATE --versions \$Latest --query 'LaunchTemplateVersions[0].LaunchTemplateData.ImageId' --output text)'",
                "InstanceType": "g4dn.xlarge",
                "SecurityGroupIds": ["'$(aws ec2 describe-launch-template-versions --launch-template-id $LAUNCH_TEMPLATE --versions \$Latest --query 'LaunchTemplateVersions[0].LaunchTemplateData.SecurityGroupIds[0]' --output text)'"],
                "IamInstanceProfile": {
                    "Name": "'$(aws ec2 describe-launch-template-versions --launch-template-id $LAUNCH_TEMPLATE --versions \$Latest --query 'LaunchTemplateVersions[0].LaunchTemplateData.IamInstanceProfile.Name' --output text)'"
                },
                "UserData": "'$(aws ec2 describe-launch-template-versions --launch-template-id $LAUNCH_TEMPLATE --versions \$Latest --query 'LaunchTemplateVersions[0].LaunchTemplateData.UserData' --output text)'",
                "BlockDeviceMappings": [
                    {
                        "DeviceName": "/dev/sda1",
                        "Ebs": {
                            "VolumeSize": 200,
                            "VolumeType": "gp3",
                            "Encrypted": true
                        }
                    }
                ],
                "TagSpecifications": [
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Name", "Value": "harness-training-ondemand-'$(date +%Y%m%d-%H%M%S)'"},
                            {"Key": "Type", "Value": "training"},
                            {"Key": "Billing", "Value": "on-demand"}
                        ]
                    }
                ]
            }' \
            --query 'LaunchTemplate.LaunchTemplateId' \
            --output text \
            --profile $AWS_PROFILE \
            --region $AWS_REGION)
        
        INSTANCE_ID=$(aws ec2 run-instances \
            --launch-template LaunchTemplateId=$LAUNCH_TEMPLATE_ON_DEMAND,Version=\$Latest \
            --subnet-id $SUBNET_ID \
            --query 'Instances[0].InstanceId' \
            --output text \
            --profile $AWS_PROFILE \
            --region $AWS_REGION)
        
        echo -e "${YELLOW}⚠️  Using on-demand instance (higher cost: ~\$1.20/hr vs \$0.30/hr spot)${NC}"
        echo -e "${YELLOW}⚠️  Training will auto-shutdown at 42 hours to stay under \$50 limit${NC}"
    }
    
    echo "Launched instance: $INSTANCE_ID"
    
    # Wait for instance to be running
    echo "Waiting for instance to start..."
    aws ec2 wait instance-running --instance-ids $INSTANCE_ID --profile $AWS_PROFILE --region $AWS_REGION
    
    # Get instance details
    INSTANCE_INFO=$(aws ec2 describe-instances \
        --instance-ids $INSTANCE_ID \
        --query 'Reservations[0].Instances[0].[PrivateIpAddress,PublicIpAddress,InstanceType]' \
        --output text \
        --profile $AWS_PROFILE \
        --region $AWS_REGION)
    
    PRIVATE_IP=$(echo $INSTANCE_INFO | cut -d' ' -f1)
    PUBLIC_IP=$(echo $INSTANCE_INFO | cut -d' ' -f2)
    INSTANCE_TYPE=$(echo $INSTANCE_INFO | cut -d' ' -f3)
    
    echo -e "${GREEN}✓ Training instance launched${NC}"
    echo "  Instance ID: $INSTANCE_ID"
    echo "  Instance Type: $INSTANCE_TYPE"
    echo "  Private IP: $PRIVATE_IP"
    echo ""
    
    # Save instance info
    cat > "$PROJECT_ROOT/.training-instance.json" <<EOF
{
    "instance_id": "$INSTANCE_ID",
    "instance_type": "$INSTANCE_TYPE",
    "private_ip": "$PRIVATE_IP",
    "launched_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "environment": "$ENVIRONMENT"
}
EOF
    
    echo $INSTANCE_ID
}

# Function to start training job
start_training_job() {
    local INSTANCE_ID=$1
    
    echo -e "${YELLOW}Starting training job on instance...${NC}"
    
    # Get S3 buckets
    TRAINING_BUCKET=$(terraform -chdir=infrastructure/terraform output -json s3_buckets | jq -r '.training_data' 2>/dev/null)
    MODEL_BUCKET=$(terraform -chdir=infrastructure/terraform output -json s3_buckets | jq -r '.model_artifacts' 2>/dev/null)
    
    # Create training configuration
    cat > /tmp/training_config.json <<EOF
{
    "model_name": "medgemma-27b",
    "training_data_path": "s3://$TRAINING_BUCKET/datasets/veterinary_qa_v1",
    "output_path": "s3://$MODEL_BUCKET/checkpoints/medgemma-27b-vet-it-$(date +%Y%m%d-%H%M%S)",
    "num_epochs": 3,
    "batch_size": 4,
    "learning_rate": 2e-5,
    "warmup_steps": 1000,
    "lora_rank": 64,
    "lora_alpha": 128,
    "wandb_project": "harness-medgemma",
    "experiment_name": "medgemma-vet-finetuning-$(date +%Y%m%d)"
}
EOF
    
    # Upload config to S3
    aws s3 cp /tmp/training_config.json "s3://$TRAINING_BUCKET/configs/current_training.json" --profile $AWS_PROFILE
    
    # SSM command to start training
    COMMAND_ID=$(aws ssm send-command \
        --instance-ids $INSTANCE_ID \
        --document-name "AWS-RunShellScript" \
        --parameters 'commands=[
            "cd /opt/harness",
            "aws s3 cp s3://'$TRAINING_BUCKET'/configs/current_training.json ./training_config.json",
            "aws s3 cp s3://'$TRAINING_BUCKET'/scripts/train_medgemma_vet.py ./",
            "nohup python train_medgemma_vet.py --config ./training_config.json > training.log 2>&1 &",
            "echo Training started with PID: $!"
        ]' \
        --output text \
        --query 'Command.CommandId' \
        --profile $AWS_PROFILE \
        --region $AWS_REGION)
    
    echo "SSM Command ID: $COMMAND_ID"
    
    # Wait for command to complete
    sleep 10
    
    # Check command status
    STATUS=$(aws ssm get-command-invocation \
        --command-id $COMMAND_ID \
        --instance-id $INSTANCE_ID \
        --query 'Status' \
        --output text \
        --profile $AWS_PROFILE \
        --region $AWS_REGION)
    
    echo "Command status: $STATUS"
    
    if [ "$STATUS" == "Success" ]; then
        echo -e "${GREEN}✓ Training job started successfully${NC}"
    else
        echo -e "${RED}Failed to start training job${NC}"
        exit 1
    fi
}

# Function to monitor training
monitor_training() {
    local INSTANCE_ID=$1
    
    echo -e "${YELLOW}Monitoring training progress...${NC}"
    echo "You can monitor the training in several ways:"
    echo ""
    echo "1. Weights & Biases:"
    echo "   https://wandb.ai/harness/harness-medgemma"
    echo ""
    echo "2. CloudWatch Logs:"
    echo "   https://console.aws.amazon.com/cloudwatch/home?region=$AWS_REGION#logsV2:log-groups/log-group/\$252Faws\$252Fharness\$252Ftraining\$252F$ENVIRONMENT"
    echo ""
    echo "3. SSH to instance (through bastion):"
    echo "   aws ssm start-session --target $INSTANCE_ID --profile $AWS_PROFILE --region $AWS_REGION"
    echo ""
    echo "4. Check GPU utilization:"
    echo "   aws ssm send-command --instance-ids $INSTANCE_ID --document-name \"AWS-RunShellScript\" --parameters 'commands=[\"nvidia-smi\"]' --profile $AWS_PROFILE --region $AWS_REGION"
}

# Function to stop training instance
stop_training_instance() {
    if [ -f "$PROJECT_ROOT/.training-instance.json" ]; then
        INSTANCE_ID=$(jq -r '.instance_id' "$PROJECT_ROOT/.training-instance.json")
        
        echo -e "${YELLOW}Stopping training instance $INSTANCE_ID...${NC}"
        
        aws ec2 terminate-instances \
            --instance-ids $INSTANCE_ID \
            --profile $AWS_PROFILE \
            --region $AWS_REGION
        
        rm "$PROJECT_ROOT/.training-instance.json"
        
        echo -e "${GREEN}✓ Training instance terminated${NC}"
    else
        echo "No active training instance found"
    fi
}

# Main function
main() {
    case "${1:-start}" in
        start)
            echo -e "${GREEN}Starting MedGemma training...${NC}"
            
            # Check if instance already exists
            if [ -f "$PROJECT_ROOT/.training-instance.json" ]; then
                INSTANCE_ID=$(jq -r '.instance_id' "$PROJECT_ROOT/.training-instance.json")
                
                # Validate instance ID is not empty
                if [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" == "null" ] || [ "$INSTANCE_ID" == "" ]; then
                    echo -e "${YELLOW}Found corrupted training instance file, removing...${NC}"
                    rm "$PROJECT_ROOT/.training-instance.json"
                else
                    # Check if instance actually exists and is running
                    INSTANCE_STATE=$(aws ec2 describe-instances \
                        --instance-ids $INSTANCE_ID \
                        --query 'Reservations[0].Instances[0].State.Name' \
                        --output text \
                        --profile $AWS_PROFILE \
                        --region $AWS_REGION 2>/dev/null || echo "not-found")
                    
                    if [ "$INSTANCE_STATE" == "running" ] || [ "$INSTANCE_STATE" == "pending" ]; then
                        echo -e "${YELLOW}Training instance already exists${NC}"
                        echo "Instance ID: $INSTANCE_ID"
                        echo "State: $INSTANCE_STATE"
                        monitor_training $INSTANCE_ID
                        exit 0
                    else
                        echo -e "${YELLOW}Previous instance ($INSTANCE_ID) is $INSTANCE_STATE, cleaning up...${NC}"
                        rm "$PROJECT_ROOT/.training-instance.json"
                    fi
                fi
            fi
            
            # Launch new instance
            INSTANCE_ID=$(launch_training_instance)
            
            # Wait a bit for instance to initialize
            echo "Waiting for instance to initialize..."
            sleep 60
            
            # Start training
            start_training_job $INSTANCE_ID
            
            # Show monitoring info
            monitor_training $INSTANCE_ID
            ;;
            
        stop)
            stop_training_instance
            ;;
            
        status)
            if [ -f "$PROJECT_ROOT/.training-instance.json" ]; then
                echo -e "${GREEN}Active training instance:${NC}"
                cat "$PROJECT_ROOT/.training-instance.json" | jq .
                
                INSTANCE_ID=$(jq -r '.instance_id' "$PROJECT_ROOT/.training-instance.json")
                
                # Check instance status
                STATUS=$(aws ec2 describe-instances \
                    --instance-ids $INSTANCE_ID \
                    --query 'Reservations[0].Instances[0].State.Name' \
                    --output text \
                    --profile $AWS_PROFILE \
                    --region $AWS_REGION 2>/dev/null || echo "terminated")
                
                echo "Instance status: $STATUS"
                
                if [ "$STATUS" == "running" ]; then
                    monitor_training $INSTANCE_ID
                fi
            else
                echo "No active training instance found"
            fi
            ;;
            
        *)
            echo "Usage: $0 {start|stop|status}"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"