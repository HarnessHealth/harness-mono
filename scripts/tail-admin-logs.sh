#!/bin/bash
# Tail Admin Frontend Logs Script

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Harness Admin Frontend Log Monitor${NC}"
echo "=================================="

# Get Terraform outputs
cd "$(dirname "$0")/../infrastructure/terraform"

CLOUDFRONT_ID=$(terraform output -raw admin_cloudfront_distribution_id 2>/dev/null || echo "")
ADMIN_BUCKET=$(terraform output -raw admin_frontend_bucket 2>/dev/null || echo "")

if [ -z "$CLOUDFRONT_ID" ]; then
    echo -e "${RED}CloudFront distribution not found. Deploy infrastructure first.${NC}"
    exit 1
fi

echo "CloudFront Distribution: $CLOUDFRONT_ID"
echo "S3 Bucket: $ADMIN_BUCKET"
echo ""

# Function to monitor CloudFront metrics
monitor_cloudfront() {
    echo -e "${YELLOW}Monitoring CloudFront metrics...${NC}"
    while true; do
        # Get request count for last 5 minutes
        REQUESTS=$(aws cloudwatch get-metric-statistics \
            --namespace AWS/CloudFront \
            --metric-name Requests \
            --dimensions Name=DistributionId,Value=$CLOUDFRONT_ID \
            --start-time $(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%S) \
            --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
            --period 300 \
            --statistics Sum \
            --query 'Datapoints[0].Sum' \
            --output text 2>/dev/null || echo "0")
        
        # Get error rate
        ERRORS=$(aws cloudwatch get-metric-statistics \
            --namespace AWS/CloudFront \
            --metric-name 4xxErrorRate \
            --dimensions Name=DistributionId,Value=$CLOUDFRONT_ID \
            --start-time $(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%S) \
            --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
            --period 300 \
            --statistics Average \
            --query 'Datapoints[0].Average' \
            --output text 2>/dev/null || echo "0")
        
        # Display current status
        echo -e "$(date): Requests: ${GREEN}${REQUESTS:-0}${NC}, 4xx Errors: ${RED}${ERRORS:-0}%${NC}"
        
        sleep 30
    done
}

# Function to tail S3 access logs (if they exist)
tail_s3_logs() {
    echo -e "${YELLOW}Checking for S3 access logs...${NC}"
    LOG_BUCKET="${ADMIN_BUCKET%-*}-logs-${ADMIN_BUCKET##*-}"
    
    # Check if logs bucket exists
    if aws s3 ls "s3://$LOG_BUCKET" >/dev/null 2>&1; then
        echo "Found logs bucket: $LOG_BUCKET"
        
        # Download and tail recent logs
        mkdir -p /tmp/cloudfront-logs
        aws s3 sync "s3://$LOG_BUCKET/cloudfront-logs/" /tmp/cloudfront-logs/ --quiet
        
        if [ -n "$(ls -A /tmp/cloudfront-logs 2>/dev/null)" ]; then
            echo -e "${GREEN}Tailing CloudFront access logs...${NC}"
            tail -f /tmp/cloudfront-logs/*.gz &
            TAIL_PID=$!
            
            # Sync new logs every minute
            while true; do
                sleep 60
                aws s3 sync "s3://$LOG_BUCKET/cloudfront-logs/" /tmp/cloudfront-logs/ --quiet
            done
        else
            echo "No log files found yet."
        fi
    else
        echo "Logs bucket not found: $LOG_BUCKET"
    fi
}

# Main menu
echo "Choose monitoring option:"
echo "1) Monitor CloudFront metrics (real-time)"
echo "2) Tail S3 access logs (if available)"
echo "3) Both"
read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        monitor_cloudfront
        ;;
    2)
        tail_s3_logs
        ;;
    3)
        monitor_cloudfront &
        MONITOR_PID=$!
        tail_s3_logs &
        TAIL_PID=$!
        
        # Wait for Ctrl+C
        trap "kill $MONITOR_PID $TAIL_PID 2>/dev/null; exit" INT
        wait
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac