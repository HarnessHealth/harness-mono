#!/bin/bash
# Script to set Terraform variables from environment

# Export Terraform variables from environment
export TF_VAR_huggingface_access_token=$HUGGINGFACE_ACCESS_TOKEN

echo "Setting Terraform variables from environment..."
echo "TF_VAR_huggingface_access_token is set: $([ -n "$TF_VAR_huggingface_access_token" ] && echo "✓" || echo "✗")"

if [ -z "$HUGGINGFACE_ACCESS_TOKEN" ]; then
    echo "⚠️  HUGGINGFACE_ACCESS_TOKEN environment variable is not set!"
    echo "   Please set it with: export HUGGINGFACE_ACCESS_TOKEN=your_token_here"
    exit 1
fi

echo "✅ Ready to run Terraform commands"