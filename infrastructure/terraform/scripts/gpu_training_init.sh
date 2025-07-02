#!/bin/bash
# GPU Training Instance Initialization with Cost Controls
# This script ensures training jobs never exceed $50

set -e

# Configuration from Terraform
MAX_RUNTIME_HOURS=${max_runtime_hours}
COST_LIMIT_DOLLARS=${cost_limit_dollars}
PROJECT_NAME=${project_name}
ENVIRONMENT=${environment}

# Instance metadata
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
INSTANCE_TYPE=$(curl -s http://169.254.169.254/latest/meta-data/instance-type)
AZ=$(curl -s http://169.254.169.254/latest/meta-data/placement/availability-zone)
REGION=$(echo $AZ | sed 's/[a-z]$//')

# Logging
LOG_FILE="/var/log/harness-training-cost-monitor.log"
exec 1> >(tee -a $LOG_FILE)
exec 2> >(tee -a $LOG_FILE >&2)

echo "=== Harness Training Cost Monitor Started ==="
echo "Instance: $INSTANCE_ID ($INSTANCE_TYPE) in $AZ"
echo "Max Runtime: $MAX_RUNTIME_HOURS hours"
echo "Cost Limit: \$$COST_LIMIT_DOLLARS"
echo "Started at: $(date)"

# Update system
apt-get update
apt-get install -y htop nvtop tmux awscli jq bc

# Configure AWS CLI
aws configure set default.region ${aws_region}

# Install additional Python packages for training
pip3 install -U \
    wandb \
    mlflow \
    deepspeed \
    bitsandbytes \
    peft \
    trl \
    accelerate \
    datasets \
    evaluate

# Create working directories
mkdir -p /opt/harness/{models,data,logs,checkpoints}

# Download training scripts from S3
aws s3 sync s3://${s3_training_bucket}/scripts /opt/harness/scripts

# Set up MLflow tracking
export MLFLOW_TRACKING_URI="http://mlflow.${project_name}.internal:5000"
export MLFLOW_S3_ENDPOINT_URL="https://s3.amazonaws.com"

# Configure Weights & Biases
if [ -n "${wandb_api_key}" ]; then
    wandb login --relogin "${wandb_api_key}" || echo "Warning: Could not login to Weights & Biases"
else
    echo "No Weights & Biases API key provided, skipping login"
fi

# Set up NVIDIA settings for optimal performance
nvidia-smi -pm 1
nvidia-smi -ac 1215,1410

# Create cost monitoring script
cat > /usr/local/bin/cost-monitor.sh << 'EOF'
#!/bin/bash
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
REGION=$(curl -s http://169.254.169.254/latest/meta-data/placement/availability-zone | sed 's/[a-z]$//')

# Calculate runtime and estimated cost
START_TIME=$(aws ec2 describe-instances --instance-ids $INSTANCE_ID --region $REGION \
  --query 'Reservations[0].Instances[0].LaunchTime' --output text)
START_EPOCH=$(date -d "$START_TIME" +%s)
CURRENT_EPOCH=$(date +%s)
RUNTIME_HOURS=$(( (CURRENT_EPOCH - START_EPOCH) / 3600 ))

# Get spot price (approximate cost)
SPOT_PRICE=$(aws ec2 describe-spot-price-history --instance-types $(curl -s http://169.254.169.254/latest/meta-data/instance-type) \
  --product-descriptions "Linux/UNIX" --region $REGION --max-items 1 \
  --query 'SpotPriceHistory[0].SpotPrice' --output text)

ESTIMATED_COST=$(echo "$RUNTIME_HOURS * $SPOT_PRICE" | bc -l)

echo "$(date): Runtime: $RUNTIME_HOURS hours, Spot Price: \$$SPOT_PRICE/hour, Estimated Cost: \$$ESTIMATED_COST"

# Check limits (100 hours max, $50 max)
if (( $(echo "$RUNTIME_HOURS >= 100" | bc -l) )); then
    echo "⚠️ RUNTIME LIMIT EXCEEDED: $RUNTIME_HOURS >= 100 hours"
    echo "💰 Estimated cost: \$$ESTIMATED_COST"
    echo "🛑 Shutting down instance to prevent overcharges..."
    aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region $REGION
    exit 1
fi

if (( $(echo "$ESTIMATED_COST >= 50" | bc -l) )); then
    echo "⚠️ COST LIMIT EXCEEDED: \$$ESTIMATED_COST >= \$50"
    echo "🛑 Shutting down instance to prevent overcharges..."
    aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region $REGION
    exit 1
fi

echo "✅ Within limits: $RUNTIME_HOURS/100 hours, \$$ESTIMATED_COST/\$50"
EOF

chmod +x /usr/local/bin/cost-monitor.sh

# Set up cron job to check cost every 15 minutes
cat > /etc/cron.d/cost-monitor << EOF
# Cost monitoring - check every 15 minutes
*/15 * * * * root /usr/local/bin/cost-monitor.sh >> $LOG_FILE 2>&1
EOF

# Create safe training wrapper
cat > /usr/local/bin/safe-training.sh << 'EOF'
#!/bin/bash
echo "🚀 Starting safe training session..."
echo "📊 Cost monitoring active - will auto-shutdown at 100 hours or \$50"
echo "🔍 Monitor costs with: tail -f /var/log/harness-training-cost-monitor.log"
echo ""
/usr/local/bin/cost-monitor.sh
EOF

chmod +x /usr/local/bin/safe-training.sh

# Create systemd service for training monitor
cat > /etc/systemd/system/harness-training-monitor.service <<EOF
[Unit]
Description=Harness Training Monitor
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/harness
ExecStart=/usr/bin/python3 /opt/harness/scripts/training_monitor.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/harness-training.log
StandardError=append:/var/log/harness-training-error.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable harness-training-monitor.service
systemctl start harness-training-monitor.service

# Log startup completion
echo "GPU training instance initialized successfully" | logger -t harness-init