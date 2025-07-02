#!/bin/bash
# Admin Frontend Deployment Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
AWS_REGION=${AWS_REGION:-us-east-1}
AWS_PROFILE=${AWS_PROFILE:-default}
ENVIRONMENT=${ENVIRONMENT:-production}

echo -e "${GREEN}Harness Admin Frontend Deployment${NC}"
echo "=================================="
echo "Environment: $ENVIRONMENT"
echo "AWS Region: $AWS_REGION"
echo "AWS Profile: $AWS_PROFILE"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v aws &> /dev/null; then
    echo -e "${RED}AWS CLI is not installed. Please install it first.${NC}"
    exit 1
fi

if ! command -v npm &> /dev/null; then
    echo -e "${RED}npm is not installed. Please install Node.js and npm first.${NC}"
    exit 1
fi

if ! aws sts get-caller-identity --profile $AWS_PROFILE &> /dev/null; then
    echo -e "${RED}AWS credentials not configured. Please run 'aws configure'.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ All prerequisites met${NC}"

# Build the frontend
echo -e "${YELLOW}Building admin frontend...${NC}"
npm install
npm run build

# Get S3 bucket and CloudFront distribution ID
echo -e "${YELLOW}Getting deployment targets...${NC}"

# Try to get from Terraform outputs first
if [ -f "$PROJECT_ROOT/infrastructure/terraform-outputs.json" ]; then
    ADMIN_BUCKET=$(cat "$PROJECT_ROOT/infrastructure/terraform-outputs.json" | jq -r '.admin_frontend_bucket.value // empty' 2>/dev/null || echo "")
    CLOUDFRONT_ID=$(cat "$PROJECT_ROOT/infrastructure/terraform-outputs.json" | jq -r '.admin_cloudfront_distribution_id.value // empty' 2>/dev/null || echo "")
fi

# If not found, try Terraform directly
if [ -z "$ADMIN_BUCKET" ] && [ -d "$PROJECT_ROOT/infrastructure/terraform" ]; then
    echo "Trying to get bucket from Terraform state..."
    cd "$PROJECT_ROOT/infrastructure/terraform"
    ADMIN_BUCKET=$(terraform output -raw admin_frontend_bucket 2>/dev/null || echo "")
    CLOUDFRONT_ID=$(terraform output -raw admin_cloudfront_distribution_id 2>/dev/null || echo "")
    cd "$SCRIPT_DIR"
fi

# If still not found, use default naming
if [ -z "$ADMIN_BUCKET" ]; then
    echo "Using default bucket naming convention..."
    ACCOUNT_ID=$(aws sts get-caller-identity --profile $AWS_PROFILE --query Account --output text)
    ADMIN_BUCKET="harness-admin-frontend-${ENVIRONMENT}-${ACCOUNT_ID}"
    
    # Check if bucket exists
    if ! aws s3api head-bucket --bucket $ADMIN_BUCKET --profile $AWS_PROFILE 2>/dev/null; then
        echo -e "${RED}Admin frontend S3 bucket not found: $ADMIN_BUCKET${NC}"
        echo "Please deploy infrastructure first using the main deploy script."
        exit 1
    fi
fi

echo "S3 Bucket: $ADMIN_BUCKET"
if [ -n "$CLOUDFRONT_ID" ]; then
    echo "CloudFront Distribution: $CLOUDFRONT_ID"
fi

# Upload to S3
echo -e "${YELLOW}Deploying to S3...${NC}"
aws s3 sync dist/ "s3://$ADMIN_BUCKET/" \
    --profile $AWS_PROFILE \
    --delete \
    --exclude ".DS_Store" \
    --exclude ".git/*" \
    --exclude "node_modules/*"

# Set cache headers for different file types
echo -e "${YELLOW}Setting cache headers...${NC}"

# HTML files - no cache
aws s3 cp "s3://$ADMIN_BUCKET/" "s3://$ADMIN_BUCKET/" \
    --profile $AWS_PROFILE \
    --exclude "*" \
    --include "*.html" \
    --include "index.html" \
    --recursive \
    --metadata-directive REPLACE \
    --content-type "text/html; charset=utf-8" \
    --cache-control "no-cache, no-store, must-revalidate"

# JS and CSS files - cache for 1 year (they have hashed names)
aws s3 cp "s3://$ADMIN_BUCKET/" "s3://$ADMIN_BUCKET/" \
    --profile $AWS_PROFILE \
    --exclude "*" \
    --include "*.js" \
    --recursive \
    --metadata-directive REPLACE \
    --content-type "application/javascript" \
    --cache-control "public, max-age=31536000, immutable"

aws s3 cp "s3://$ADMIN_BUCKET/" "s3://$ADMIN_BUCKET/" \
    --profile $AWS_PROFILE \
    --exclude "*" \
    --include "*.css" \
    --recursive \
    --metadata-directive REPLACE \
    --content-type "text/css" \
    --cache-control "public, max-age=31536000, immutable"

# Images and other assets - cache for 1 week
aws s3 cp "s3://$ADMIN_BUCKET/" "s3://$ADMIN_BUCKET/" \
    --profile $AWS_PROFILE \
    --exclude "*" \
    --include "*.png" \
    --include "*.jpg" \
    --include "*.jpeg" \
    --include "*.gif" \
    --include "*.svg" \
    --include "*.ico" \
    --recursive \
    --metadata-directive REPLACE \
    --cache-control "public, max-age=604800"

# Invalidate CloudFront cache
if [ -n "$CLOUDFRONT_ID" ]; then
    echo -e "${YELLOW}Invalidating CloudFront cache...${NC}"
    INVALIDATION_ID=$(aws cloudfront create-invalidation \
        --distribution-id $CLOUDFRONT_ID \
        --paths "/*" \
        --profile $AWS_PROFILE \
        --query "Invalidation.Id" \
        --output text)
    
    echo "Invalidation ID: $INVALIDATION_ID"
    echo -e "${GREEN}✓ CloudFront cache invalidation started${NC}"
fi

echo ""
echo -e "${GREEN}🎉 Admin frontend deployed successfully!${NC}"
echo ""
echo "Access the admin frontend at:"
echo "  https://admin.harness.health"
echo ""

# Show deployment info
echo "Deployment summary:"
echo "  - S3 Bucket: $ADMIN_BUCKET"
if [ -n "$CLOUDFRONT_ID" ]; then
    echo "  - CloudFront Distribution: $CLOUDFRONT_ID"
    echo "  - Invalidation ID: $INVALIDATION_ID"
fi
echo "  - Environment: $ENVIRONMENT"
echo "  - Deployed at: $(date)"