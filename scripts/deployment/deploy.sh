#!/bin/bash
# Harness Infrastructure Deployment Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ENVIRONMENT=${ENVIRONMENT:-development}
AWS_REGION=${AWS_REGION:-us-east-1}
AWS_PROFILE=${AWS_PROFILE:-default}

# Parse command line arguments
COMPONENT=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --admin-frontend|--admin)
            COMPONENT="admin-frontend"
            shift
            ;;
        --backend)
            COMPONENT="backend"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --admin-frontend, --admin    Deploy only the admin frontend"
            echo "  --backend                    Deploy only the backend services"
            echo "  --help, -h                   Show this help message"
            echo ""
            echo "Without options, deploys entire infrastructure"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}Harness Infrastructure Deployment${NC}"
echo "=================================="
echo "Environment: $ENVIRONMENT"
echo "AWS Region: $AWS_REGION"
echo "AWS Profile: $AWS_PROFILE"
if [ -n "$COMPONENT" ]; then
    echo "Component: $COMPONENT"
fi
echo ""

# Function to check prerequisites
check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        echo -e "${RED}AWS CLI is not installed. Please install it first.${NC}"
        exit 1
    fi
    
    # Check Terraform
    if ! command -v terraform &> /dev/null; then
        echo -e "${RED}Terraform is not installed. Please install it first.${NC}"
        exit 1
    fi
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Docker is not installed. Please install it first.${NC}"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity --profile $AWS_PROFILE &> /dev/null; then
        echo -e "${RED}AWS credentials not configured. Please run 'aws configure'.${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✓ All prerequisites met${NC}"
}

# Function to create S3 bucket for Terraform state
create_terraform_backend() {
    echo -e "${YELLOW}Setting up Terraform backend...${NC}"
    
    BUCKET_NAME="harness-terraform-state-285641110801"
    
    # Check if bucket exists
    if aws s3api head-bucket --bucket $BUCKET_NAME --profile $AWS_PROFILE 2>/dev/null; then
        echo "Terraform state bucket already exists"
    else
        echo "Creating Terraform state bucket..."
        aws s3api create-bucket \
            --bucket $BUCKET_NAME \
            --region $AWS_REGION \
            --profile $AWS_PROFILE
        
        # Enable versioning
        aws s3api put-bucket-versioning \
            --bucket $BUCKET_NAME \
            --versioning-configuration Status=Enabled \
            --profile $AWS_PROFILE
        
        # Enable encryption
        aws s3api put-bucket-encryption \
            --bucket $BUCKET_NAME \
            --server-side-encryption-configuration '{
                "Rules": [{
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "AES256"
                    }
                }]
            }' \
            --profile $AWS_PROFILE
        
        echo -e "${GREEN}✓ Terraform state bucket created${NC}"
    fi
}

# Function to deploy infrastructure with Terraform
deploy_infrastructure() {
    echo -e "${YELLOW}Deploying infrastructure with Terraform...${NC}"
    
    cd "$PROJECT_ROOT/infrastructure/terraform"
    
    # Initialize Terraform
    terraform init \
        -backend-config="bucket=harness-terraform-state-285641110801" \
        -backend-config="key=harness/terraform.tfstate" \
        -backend-config="region=$AWS_REGION"
    
    # Create terraform.tfvars if it doesn't exist
    if [ ! -f terraform.tfvars ]; then
        cat > terraform.tfvars <<EOF
aws_region = "$AWS_REGION"
environment = "$ENVIRONMENT"
project_name = "harness"
EOF
    fi
    
    # Plan deployment
    echo -e "${YELLOW}Planning infrastructure changes...${NC}"
    terraform plan -out=tfplan
    
    # Apply changes
    read -p "Do you want to apply these changes? (yes/no): " -n 3 -r
    echo
    if [[ $REPLY =~ ^yes$ ]]; then
        terraform apply tfplan
        echo -e "${GREEN}✓ Infrastructure deployed successfully${NC}"
    else
        echo -e "${RED}Deployment cancelled${NC}"
        rm tfplan
        exit 1
    fi
    
    # Save outputs
    terraform output -json > "$PROJECT_ROOT/infrastructure/terraform-outputs.json"
}

# Function to build and deploy admin frontend
deploy_admin_frontend() {
    echo -e "${YELLOW}Deploying admin frontend...${NC}"
    
    cd "$PROJECT_ROOT/admin-frontend"
    
    # Check if npm is installed
    if ! command -v npm &> /dev/null; then
        echo -e "${RED}npm is not installed. Please install Node.js and npm first.${NC}"
        exit 1
    fi
    
    # Install dependencies
    echo "Installing dependencies..."
    npm install
    
    # Build the frontend
    echo "Building admin frontend..."
    npm run build
    
    # Get S3 bucket for admin frontend from Terraform outputs
    if [ -f "$PROJECT_ROOT/infrastructure/terraform-outputs.json" ]; then
        ADMIN_BUCKET=$(cat "$PROJECT_ROOT/infrastructure/terraform-outputs.json" | jq -r '.admin_frontend_bucket.value // empty' 2>/dev/null || echo "")
        CLOUDFRONT_ID=$(cat "$PROJECT_ROOT/infrastructure/terraform-outputs.json" | jq -r '.admin_cloudfront_distribution_id.value // empty' 2>/dev/null || echo "")
    fi
    
    if [ -z "$ADMIN_BUCKET" ]; then
        # Try to get it directly from Terraform
        if [ -d "$PROJECT_ROOT/infrastructure/terraform" ]; then
            ADMIN_BUCKET=$(terraform -chdir="$PROJECT_ROOT/infrastructure/terraform" output -raw admin_frontend_bucket 2>/dev/null || echo "")
            CLOUDFRONT_ID=$(terraform -chdir="$PROJECT_ROOT/infrastructure/terraform" output -raw admin_cloudfront_distribution_id 2>/dev/null || echo "")
        fi
    fi
    
    if [ -z "$ADMIN_BUCKET" ]; then
        echo -e "${RED}Admin frontend S3 bucket not found. Please deploy infrastructure first.${NC}"
        exit 1
    fi
    
    # Upload to S3
    echo "Uploading to S3 bucket: $ADMIN_BUCKET..."
    aws s3 sync dist/ "s3://$ADMIN_BUCKET/" \
        --profile $AWS_PROFILE \
        --delete \
        --exclude ".git/*" \
        --exclude "node_modules/*"
    
    # Set proper content types
    aws s3 cp "s3://$ADMIN_BUCKET/" "s3://$ADMIN_BUCKET/" \
        --profile $AWS_PROFILE \
        --exclude "*" \
        --include "*.html" \
        --recursive \
        --metadata-directive REPLACE \
        --content-type "text/html; charset=utf-8"
    
    aws s3 cp "s3://$ADMIN_BUCKET/" "s3://$ADMIN_BUCKET/" \
        --profile $AWS_PROFILE \
        --exclude "*" \
        --include "*.js" \
        --recursive \
        --metadata-directive REPLACE \
        --content-type "application/javascript"
    
    aws s3 cp "s3://$ADMIN_BUCKET/" "s3://$ADMIN_BUCKET/" \
        --profile $AWS_PROFILE \
        --exclude "*" \
        --include "*.css" \
        --recursive \
        --metadata-directive REPLACE \
        --content-type "text/css"
    
    # Invalidate CloudFront cache if distribution ID is available
    if [ -n "$CLOUDFRONT_ID" ]; then
        echo "Invalidating CloudFront cache..."
        aws cloudfront create-invalidation \
            --distribution-id $CLOUDFRONT_ID \
            --paths "/*" \
            --profile $AWS_PROFILE
        echo -e "${GREEN}✓ CloudFront cache invalidated${NC}"
    fi
    
    echo -e "${GREEN}✓ Admin frontend deployed successfully${NC}"
    echo ""
    echo "Admin frontend URL: https://admin.harness.health"
}

# Function to build and push Docker images
build_docker_images() {
    echo -e "${YELLOW}Building Docker images...${NC}"
    
    # Use the optimized fast-build script
    if [ -f "$PROJECT_ROOT/scripts/deployment/fast-build.sh" ]; then
        echo "Using optimized build process..."
        "$PROJECT_ROOT/scripts/deployment/fast-build.sh" backend
        "$PROJECT_ROOT/scripts/deployment/fast-build.sh" lambda
    else
        # Fallback to original method
        cd "$PROJECT_ROOT"
        
        # Get ECR repository URL from Terraform outputs
        ECR_REPO=$(terraform -chdir=infrastructure/terraform output -raw ecr_repository_url 2>/dev/null || echo "")
        
        if [ -z "$ECR_REPO" ]; then
            echo -e "${YELLOW}ECR repository not found, skipping Docker build${NC}"
            return
        fi
        
        # Login to ECR
        aws ecr get-login-password --region $AWS_REGION --profile $AWS_PROFILE | \
            docker login --username AWS --password-stdin $ECR_REPO
        
        # Build backend image
        echo "Building backend image..."
        docker build -f infrastructure/docker/Dockerfile.backend -t harness-backend:latest .
        docker tag harness-backend:latest $ECR_REPO:backend-latest
        docker push $ECR_REPO:backend-latest
        
        # Build GROBID processor Lambda
        echo "Building GROBID processor Lambda..."
        cd "$PROJECT_ROOT/data-pipeline/lambdas/grobid_processor"
        docker build -t harness-grobid-processor:latest .
        docker tag harness-grobid-processor:latest $ECR_REPO:grobid-processor-latest
        docker push $ECR_REPO:grobid-processor-latest
    fi
    
    echo -e "${GREEN}✓ Docker images built and pushed${NC}"
}

# Function to deploy Lambda functions
deploy_lambda_functions() {
    echo -e "${YELLOW}Deploying Lambda functions...${NC}"
    
    # Update GROBID processor Lambda
    FUNCTION_NAME="harness-grobid-processor-$ENVIRONMENT"
    ECR_REPO=$(terraform -chdir=infrastructure/terraform output -raw ecr_repository_url 2>/dev/null || echo "")
    
    if [ -n "$ECR_REPO" ]; then
        aws lambda update-function-code \
            --function-name $FUNCTION_NAME \
            --image-uri $ECR_REPO:grobid-processor-latest \
            --profile $AWS_PROFILE \
            --region $AWS_REGION 2>/dev/null || echo "Lambda function will be created by Terraform"
    fi
}

# Function to setup Airflow
setup_airflow() {
    echo -e "${YELLOW}Setting up Airflow...${NC}"
    
    # Get Airflow database endpoint
    AIRFLOW_DB=$(terraform -chdir=infrastructure/terraform output -raw airflow_db_endpoint 2>/dev/null || echo "")
    
    if [ -z "$AIRFLOW_DB" ]; then
        echo -e "${YELLOW}Airflow database not found, skipping Airflow setup${NC}"
        return
    fi
    
    # Copy DAGs to S3
    S3_BUCKET=$(terraform -chdir=infrastructure/terraform output -json s3_buckets | jq -r '.airflow_logs' 2>/dev/null || echo "")
    
    if [ -n "$S3_BUCKET" ]; then
        echo "Uploading DAGs to S3..."
        aws s3 sync \
            "$PROJECT_ROOT/data-pipeline/dags" \
            "s3://$S3_BUCKET/dags/" \
            --profile $AWS_PROFILE \
            --exclude "*.pyc" \
            --exclude "__pycache__/*"
    fi
    
    echo -e "${GREEN}✓ Airflow setup complete${NC}"
}

# Function to create initial S3 bucket structure
setup_s3_structure() {
    echo -e "${YELLOW}Setting up S3 bucket structure...${NC}"
    
    # Get bucket names from Terraform
    BUCKETS=$(terraform -chdir=infrastructure/terraform output -json s3_buckets 2>/dev/null || echo "{}")
    
    if [ "$BUCKETS" != "{}" ]; then
        # Create folder structure in each bucket
        for bucket_type in veterinary_corpus model_artifacts training_data embeddings; do
            BUCKET=$(echo $BUCKETS | jq -r ".$bucket_type" 2>/dev/null || echo "")
            
            if [ -n "$BUCKET" ] && [ "$BUCKET" != "null" ]; then
                echo "Setting up structure in $BUCKET..."
                
                # Create folders based on bucket type
                case $bucket_type in
                    veterinary_corpus)
                        aws s3api put-object --bucket $BUCKET --key raw/pubmed/ --profile $AWS_PROFILE
                        aws s3api put-object --bucket $BUCKET --key raw/unpaywall/ --profile $AWS_PROFILE
                        aws s3api put-object --bucket $BUCKET --key raw/conferences/ --profile $AWS_PROFILE
                        aws s3api put-object --bucket $BUCKET --key metadata/ --profile $AWS_PROFILE
                        ;;
                    model_artifacts)
                        aws s3api put-object --bucket $BUCKET --key checkpoints/ --profile $AWS_PROFILE
                        aws s3api put-object --bucket $BUCKET --key final_models/ --profile $AWS_PROFILE
                        aws s3api put-object --bucket $BUCKET --key evaluation_results/ --profile $AWS_PROFILE
                        ;;
                    training_data)
                        aws s3api put-object --bucket $BUCKET --key processed/grobid/ --profile $AWS_PROFILE
                        aws s3api put-object --bucket $BUCKET --key processed/tei/ --profile $AWS_PROFILE
                        aws s3api put-object --bucket $BUCKET --key datasets/ --profile $AWS_PROFILE
                        aws s3api put-object --bucket $BUCKET --key scripts/ --profile $AWS_PROFILE
                        ;;
                    embeddings)
                        aws s3api put-object --bucket $BUCKET --key document_embeddings/ --profile $AWS_PROFILE
                        aws s3api put-object --bucket $BUCKET --key chunk_embeddings/ --profile $AWS_PROFILE
                        ;;
                esac
            fi
        done
        
        echo -e "${GREEN}✓ S3 bucket structure created${NC}"
    fi
}

# Function to upload initial scripts
upload_scripts() {
    echo -e "${YELLOW}Uploading scripts to S3...${NC}"
    
    TRAINING_BUCKET=$(terraform -chdir=infrastructure/terraform output -json s3_buckets | jq -r '.training_data' 2>/dev/null || echo "")
    
    if [ -n "$TRAINING_BUCKET" ] && [ "$TRAINING_BUCKET" != "null" ]; then
        # Upload training scripts
        aws s3 cp \
            "$PROJECT_ROOT/data-pipeline/scripts/train_medgemma_vet.py" \
            "s3://$TRAINING_BUCKET/scripts/" \
            --profile $AWS_PROFILE
        
        # Upload crawler scripts
        aws s3 sync \
            "$PROJECT_ROOT/data-pipeline/scripts/crawlers" \
            "s3://$TRAINING_BUCKET/scripts/crawlers/" \
            --profile $AWS_PROFILE \
            --exclude "*.pyc" \
            --exclude "__pycache__/*"
        
        # Upload evaluation scripts
        aws s3 cp \
            "$PROJECT_ROOT/data-pipeline/evaluation/veterinary_benchmarks.py" \
            "s3://$TRAINING_BUCKET/scripts/" \
            --profile $AWS_PROFILE
        
        echo -e "${GREEN}✓ Scripts uploaded to S3${NC}"
    fi
}

# Main deployment flow
main() {
    echo -e "${GREEN}Starting Harness deployment...${NC}"
    echo ""
    
    # Check prerequisites
    check_prerequisites
    
    # Handle component-specific deployments
    if [ "$COMPONENT" = "admin-frontend" ]; then
        # Admin frontend only deployment
        deploy_admin_frontend
    elif [ "$COMPONENT" = "backend" ]; then
        # Backend only deployment
        build_docker_images
        deploy_lambda_functions
        echo -e "${GREEN}✓ Backend services deployed successfully${NC}"
    else
        # Full infrastructure deployment
        # Create Terraform backend
        create_terraform_backend
        
        # Deploy infrastructure
        deploy_infrastructure
        
        # Build and push Docker images
        build_docker_images
        
        # Deploy Lambda functions
        deploy_lambda_functions
        
        # Setup Airflow
        setup_airflow
        
        # Setup S3 structure
        setup_s3_structure
        
        # Upload scripts
        upload_scripts
        
        # Deploy admin frontend
        deploy_admin_frontend
        
        echo ""
        echo -e "${GREEN}🎉 Full deployment completed successfully!${NC}"
        echo ""
        echo "Next steps:"
        echo "1. Access Airflow UI to start data pipelines"
        echo "2. Launch GPU instances for model training"
        echo "3. Configure monitoring dashboards"
        echo ""
        
        # Output important endpoints
        echo "Important endpoints:"
        terraform -chdir=infrastructure/terraform output
    fi
}

# Run main function
main