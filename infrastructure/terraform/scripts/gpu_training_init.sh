#!/bin/bash
set -e

# Update system
apt-get update
apt-get install -y htop nvtop tmux

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