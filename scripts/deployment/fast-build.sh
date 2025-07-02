#!/bin/bash
# Fast Docker Build Script using BuildX and optimal caching

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

# Load environment variables from .env file if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo -e "${BLUE}Loading environment from .env file...${NC}"
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
fi

ENVIRONMENT=${ENVIRONMENT:-development}
AWS_REGION=${AWS_REGION:-us-east-1}
AWS_PROFILE=${AWS_PROFILE:-default}
USE_CODEBUILD=${USE_CODEBUILD:-false}
COMPONENT=${1:-all}

echo -e "${GREEN}Harness Fast Build System${NC}"
echo "=========================="
echo "Environment: $ENVIRONMENT"
echo "Component: $COMPONENT"
echo "Use CodeBuild: $USE_CODEBUILD"
echo ""

# Function to check if buildx is available
check_buildx() {
    if ! docker buildx version &> /dev/null; then
        echo -e "${YELLOW}Docker buildx not found. Installing...${NC}"
        docker buildx create --use --name harness-builder --driver docker-container
    else
        # Check if our builder exists
        if ! docker buildx ls | grep -q "harness-builder"; then
            echo -e "${YELLOW}Creating buildx builder...${NC}"
            docker buildx create --use --name harness-builder --driver docker-container
        else
            docker buildx use harness-builder
        fi
    fi
}

# Function to get ECR login
ecr_login() {
    echo -e "${YELLOW}Logging in to ECR...${NC}"
    aws ecr get-login-password --region $AWS_REGION --profile $AWS_PROFILE | \
        docker login --username AWS --password-stdin $ECR_REPO
}

# Function to build with CodeBuild
build_with_codebuild() {
    local project_name=$1
    
    echo -e "${YELLOW}Starting CodeBuild project: $project_name${NC}"
    
    # Create source archive as ZIP (CodeBuild expects ZIP for S3 source)
    TEMP_DIR=$(mktemp -d)
    TEMP_FILE="$TEMP_DIR/source.zip"
    cd "$PROJECT_ROOT"
    
    echo -e "${YELLOW}Creating source archive...${NC}"
    git archive --format=zip HEAD > $TEMP_FILE
    
    # Upload to S3 at the expected location
    SOURCE_BUCKET=$(aws s3api list-buckets --query "Buckets[?contains(Name, 'codebuild-cache')].Name" --output text --profile $AWS_PROFILE)
    aws s3 cp $TEMP_FILE s3://$SOURCE_BUCKET/source/source.zip --profile $AWS_PROFILE
    
    echo -e "${YELLOW}Source uploaded, starting build...${NC}"
    
    # Start build
    BUILD_ID=$(aws codebuild start-build \
        --project-name $project_name \
        --environment-variables-override \
            name=ENVIRONMENT,value=$ENVIRONMENT,type=PLAINTEXT \
            name=DEPLOY_TO_ECS,value=true,type=PLAINTEXT \
        --profile $AWS_PROFILE \
        --query 'build.id' \
        --output text)
    
    echo "Build started: $BUILD_ID"
    echo "View logs: https://console.aws.amazon.com/codesuite/codebuild/projects/$project_name/build/$BUILD_ID"
    
    # Wait for build to complete
    echo -e "${YELLOW}Waiting for build to complete...${NC}"
    
    # Poll build status until completion
    while true; do
        BUILD_STATUS=$(aws codebuild batch-get-builds --ids $BUILD_ID --query 'builds[0].buildStatus' --output text --profile $AWS_PROFILE 2>/dev/null || echo "IN_PROGRESS")
        
        case $BUILD_STATUS in
            "SUCCEEDED"|"FAILED"|"FAULT"|"STOPPED"|"TIMED_OUT")
                break
                ;;
            *)
                echo -n "."
                sleep 10
                ;;
        esac
    done
    echo ""
    
    # Check build status
    BUILD_STATUS=$(aws codebuild batch-get-builds --ids $BUILD_ID --query 'builds[0].buildStatus' --output text --profile $AWS_PROFILE)
    
    if [ "$BUILD_STATUS" = "SUCCEEDED" ]; then
        echo -e "${GREEN}✓ Build completed successfully${NC}"
    else
        echo -e "${RED}✗ Build failed with status: $BUILD_STATUS${NC}"
        exit 1
    fi
    
    # Cleanup
    rm -rf $TEMP_DIR
}

# Function to build locally with buildx
build_local() {
    local image_name=$1
    local dockerfile=$2
    local context=$3
    local target=${4:-production}
    
    echo -e "${YELLOW}Building $image_name locally with buildx...${NC}"
    
    # Build with optimal caching
    docker buildx build \
        --platform linux/amd64 \
        --cache-from type=registry,ref=$ECR_REPO:$image_name-buildcache \
        --cache-to type=registry,ref=$ECR_REPO:$image_name-buildcache,mode=max \
        --cache-from type=local,src=/tmp/.buildx-cache-$image_name \
        --cache-to type=local,dest=/tmp/.buildx-cache-$image_name,mode=max \
        --tag $ECR_REPO:$image_name-latest \
        --tag $ECR_REPO:$image_name-$(git rev-parse --short HEAD) \
        --target $target \
        --push \
        -f $dockerfile \
        $context \
        --progress=plain
}

# Main execution
main() {
    cd "$PROJECT_ROOT"
    
    # Get ECR repository
    ECR_REPO=$(terraform -chdir=infrastructure/terraform output -raw ecr_repository_url 2>/dev/null || echo "")
    
    if [ -z "$ECR_REPO" ]; then
        echo -e "${RED}ECR repository not found. Please deploy infrastructure first.${NC}"
        exit 1
    fi
    
    # Check if we should use CodeBuild
    if [ "$USE_CODEBUILD" = "true" ]; then
        # Get CodeBuild project names
        BACKEND_PROJECT=$(terraform -chdir=infrastructure/terraform output -raw codebuild_backend_project 2>/dev/null || echo "")
        LAMBDA_PROJECT=$(terraform -chdir=infrastructure/terraform output -raw codebuild_lambda_project 2>/dev/null || echo "")
        
        if [ -z "$BACKEND_PROJECT" ]; then
            echo -e "${RED}CodeBuild projects not found. Please deploy CodeBuild infrastructure.${NC}"
            exit 1
        fi
        
        case $COMPONENT in
            backend|all)
                build_with_codebuild $BACKEND_PROJECT
                ;;
            lambda)
                build_with_codebuild $LAMBDA_PROJECT
                ;;
        esac
    else
        # Local build with buildx
        check_buildx
        ecr_login
        
        case $COMPONENT in
            backend|all)
                build_local "backend" \
                    "infrastructure/docker/Dockerfile.backend.optimized" \
                    "." \
                    "production"
                    
                # Update ECS service
                echo -e "${YELLOW}Updating ECS service...${NC}"
                aws ecs update-service \
                    --cluster harness-cluster-$ENVIRONMENT \
                    --service harness-api-service-$ENVIRONMENT \
                    --force-new-deployment \
                    --profile $AWS_PROFILE \
                    --region $AWS_REGION || echo "ECS service update failed (service might not exist)"
                ;;
                
            lambda|all)
                build_local "grobid-processor" \
                    "data-pipeline/lambdas/grobid_processor/Dockerfile" \
                    "data-pipeline/lambdas/grobid_processor"
                    
                # Update Lambda function
                echo -e "${YELLOW}Updating Lambda function...${NC}"
                aws lambda update-function-code \
                    --function-name harness-grobid-processor-$ENVIRONMENT \
                    --image-uri $ECR_REPO:grobid-processor-latest \
                    --profile $AWS_PROFILE \
                    --region $AWS_REGION || echo "Lambda update failed (function might not exist)"
                ;;
                
            admin-frontend)
                echo -e "${YELLOW}Building admin frontend...${NC}"
                cd admin-frontend
                npm ci
                npm run build
                
                # Deploy to S3
                ./deploy.sh
                ;;
                
            *)
                echo -e "${RED}Unknown component: $COMPONENT${NC}"
                echo "Valid options: all, backend, lambda, admin-frontend"
                exit 1
                ;;
        esac
    fi
    
    echo ""
    echo -e "${GREEN}🚀 Build and deployment completed!${NC}"
    echo ""
    echo "Tips for faster builds:"
    echo "• Use 'USE_CODEBUILD=true $0' to build in AWS (faster for slow connections)"
    echo "• Run '$0 backend' to build only the backend"
    echo "• Run '$0 admin-frontend' to deploy only the frontend"
    echo "• Docker layer cache is preserved between builds"
}

# Show usage
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Usage: $0 [component]"
    echo ""
    echo "Components:"
    echo "  all              Build all components (default)"
    echo "  backend          Build only backend API"
    echo "  lambda           Build only Lambda functions"
    echo "  admin-frontend   Build and deploy admin frontend"
    echo ""
    echo "Environment variables:"
    echo "  USE_CODEBUILD=true   Use AWS CodeBuild instead of local build"
    echo "  ENVIRONMENT=staging  Set deployment environment"
    echo "  AWS_PROFILE=prod     Set AWS profile"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Build everything locally"
    echo "  $0 backend                            # Build only backend"
    echo "  USE_CODEBUILD=true $0                 # Build in AWS"
    echo "  ENVIRONMENT=production $0 backend     # Deploy backend to production"
    exit 0
fi

# Run main function
main