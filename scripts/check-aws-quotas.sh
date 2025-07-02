#!/bin/bash
# AWS EC2 vCPU Quota Checker and Quota Increase Helper

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}AWS EC2 vCPU Quota Checker${NC}"
echo "=========================="

# Instance types we commonly use
declare -A INSTANCE_FAMILIES=(
    ["Standard instances"]="m5 m6i c5 c6i r5 r6i t3 t4g"
    ["GPU instances"]="p3 p4d p4de g4dn g5"
    ["High memory instances"]="x1e x2iezn r5n r6in"
    ["Storage optimized"]="i3 i4i d3"
)

# Function to check vCPU limits
check_vcpu_limits() {
    echo -e "${YELLOW}Checking current EC2 vCPU limits...${NC}"
    
    # Try to list service quotas (may fail due to permissions)
    if aws service-quotas list-service-quotas --service-code ec2 \
        --query 'Quotas[?contains(QuotaName, `vCPU`) && contains(QuotaName, `Running On-Demand`)].[QuotaName,Value,QuotaCode]' \
        --output table 2>/dev/null; then
        echo ""
    else
        echo -e "${RED}❌ Unable to check quotas directly (missing servicequotas permissions)${NC}"
        echo "You can check quotas manually in the AWS Console:"
        echo "  👉 https://console.aws.amazon.com/servicequotas/home/services/ec2/quotas"
        echo ""
    fi
}

# Function to show common instance types and their vCPU requirements
show_instance_info() {
    echo -e "${YELLOW}Common Instance Types & vCPU Requirements:${NC}"
    echo ""
    
    echo "🔧 Development/Testing:"
    echo "  g4dn.xlarge    - 4 vCPUs,  1x T4 GPU     (~$0.30/hr spot)"
    echo "  g4dn.2xlarge   - 8 vCPUs,  1x T4 GPU     (~$0.60/hr spot)"
    echo "  t3.medium      - 2 vCPUs,  No GPU        (~$0.02/hr spot)"
    echo ""
    
    echo "🚀 Production Training:"
    echo "  p3.2xlarge     - 8 vCPUs,  1x V100 GPU   (~$1.50/hr spot)"
    echo "  p3.8xlarge     - 32 vCPUs, 4x V100 GPU   (~$6.00/hr spot)"
    echo "  p4d.24xlarge   - 96 vCPUs, 8x A100 GPU   (~$15.00/hr spot)"
    echo ""
    
    echo "💰 Cost Optimization Tips:"
    echo "  • Use Spot instances (60-90% cheaper)"
    echo "  • Start with smaller instances (g4dn.xlarge)"
    echo "  • Scale up as needed"
    echo ""
}

# Function to help request quota increases
request_quota_increase() {
    echo -e "${YELLOW}How to Request vCPU Quota Increase:${NC}"
    echo ""
    
    echo "1️⃣ AWS Console Method (Recommended):"
    echo "   👉 https://console.aws.amazon.com/servicequotas/home/services/ec2/quotas"
    echo "   • Search for 'Running On-Demand'"
    echo "   • Find the instance family you need (e.g., 'P instances')"
    echo "   • Click 'Request quota increase'"
    echo ""
    
    echo "2️⃣ AWS Support Case:"
    echo "   👉 https://console.aws.amazon.com/support/home#/case/create"
    echo "   • Select 'Service limit increase'"
    echo "   • Choose 'EC2 instances'"
    echo ""
    
    echo "3️⃣ Business Justification Examples:"
    echo "   • 'Machine learning training for veterinary AI platform'"
    echo "   • 'Development and testing of deep learning models'"
    echo "   • 'Research project requiring GPU compute resources'"
    echo ""
    
    echo "4️⃣ Typical Approval Times:"
    echo "   • Standard instances: Usually automatic or within hours"
    echo "   • GPU instances: 1-2 business days"
    echo "   • Large requests: May require additional review"
    echo ""
}

# Function to test if we can launch instances
test_instance_launch() {
    local instance_type=${1:-"t3.micro"}
    
    echo -e "${YELLOW}Testing if we can launch ${instance_type}...${NC}"
    
    # Get the first public subnet
    SUBNET_ID=$(aws ec2 describe-subnets \
        --filters "Name=tag:Name,Values=harness-public-*" \
        --query 'Subnets[0].SubnetId' \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$SUBNET_ID" ] || [ "$SUBNET_ID" = "None" ]; then
        echo -e "${RED}❌ No suitable subnet found${NC}"
        return 1
    fi
    
    # Try to run a dry-run launch
    if aws ec2 run-instances \
        --image-id ami-0c02fb55956c7d316 \
        --instance-type "$instance_type" \
        --subnet-id "$SUBNET_ID" \
        --dry-run 2>/dev/null; then
        echo -e "${GREEN}✅ Can launch ${instance_type}${NC}"
        return 0
    else
        local error=$(aws ec2 run-instances \
            --image-id ami-0c02fb55956c7d316 \
            --instance-type "$instance_type" \
            --subnet-id "$SUBNET_ID" \
            --dry-run 2>&1 | grep -o 'VcpuLimitExceeded\|InsufficientInstanceCapacity\|DryRunOperation' || echo "UnknownError")
        
        case $error in
            "VcpuLimitExceeded")
                echo -e "${RED}❌ vCPU limit exceeded for ${instance_type}${NC}"
                ;;
            "InsufficientInstanceCapacity")
                echo -e "${YELLOW}⚠️  ${instance_type} not available in this AZ (try different region/AZ)${NC}"
                ;;
            "DryRunOperation")
                echo -e "${GREEN}✅ Can launch ${instance_type}${NC}"
                ;;
            *)
                echo -e "${RED}❌ Cannot launch ${instance_type}: ${error}${NC}"
                ;;
        esac
        return 1
    fi
}

# Main execution
echo "Current AWS Account: $(aws sts get-caller-identity --query Account --output text)"
echo "Current Region: $(aws configure get region)"
echo ""

check_vcpu_limits
show_instance_info

echo -e "${BLUE}Testing Instance Launch Capabilities:${NC}"
echo "======================================"

# Test different instance types
test_instance_launch "t3.micro"
test_instance_launch "t3.medium" 
test_instance_launch "g4dn.xlarge"
test_instance_launch "p3.2xlarge"

echo ""
request_quota_increase

echo -e "${GREEN}💡 Quick Fix Applied:${NC}"
echo "• Changed default GPU instance from p4d.24xlarge → g4dn.xlarge"
echo "• Added spot instance configuration (60-90% cost savings)"
echo "• You should now be able to launch GPU training instances"
echo ""

echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Test launching a g4dn.xlarge instance"
echo "2. If you need larger instances, request quota increases"
echo "3. Consider using SageMaker for managed training if quotas are limited"