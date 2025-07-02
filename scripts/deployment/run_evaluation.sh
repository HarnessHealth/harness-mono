#!/bin/bash
# Harness Model Evaluation Script

set -e

# Configuration
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ENVIRONMENT=${ENVIRONMENT:-development}
AWS_REGION=${AWS_REGION:-us-east-1}
AWS_PROFILE=${AWS_PROFILE:-default}

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Harness Model Evaluation Runner${NC}"
echo "================================"
echo ""

# Function to list available models
list_models() {
    echo -e "${YELLOW}Available models:${NC}"
    
    MODEL_BUCKET=$(terraform -chdir=infrastructure/terraform output -json s3_buckets | jq -r '.model_artifacts' 2>/dev/null)
    
    if [ -n "$MODEL_BUCKET" ]; then
        aws s3 ls "s3://$MODEL_BUCKET/final_models/" --profile $AWS_PROFILE --recursive | grep -E "/$" | awk '{print $NF}'
    else
        echo "No model bucket found. Deploy infrastructure first."
        exit 1
    fi
}

# Function to run evaluation
run_evaluation() {
    local MODEL_PATH=$1
    
    if [ -z "$MODEL_PATH" ]; then
        echo -e "${RED}Please specify a model path${NC}"
        list_models
        exit 1
    fi
    
    echo -e "${YELLOW}Running evaluation for model: $MODEL_PATH${NC}"
    
    # Create evaluation job configuration
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    JOB_NAME="evaluation-$TIMESTAMP"
    
    cat > /tmp/evaluation_config.json <<EOF
{
    "job_name": "$JOB_NAME",
    "model_path": "$MODEL_PATH",
    "benchmarks": [
        "vetqa_1000",
        "navle_sample",
        "clinical_cases",
        "citation_accuracy",
        "safety",
        "species_specific"
    ],
    "output_path": "s3://$(terraform -chdir=infrastructure/terraform output -json s3_buckets | jq -r '.model_artifacts')/evaluation_results/$JOB_NAME"
}
EOF
    
    # Launch evaluation on SageMaker or EC2
    echo "Launching evaluation job..."
    
    # Option 1: Use SageMaker Processing Job
    if command -v aws sagemaker &> /dev/null; then
        ROLE_ARN=$(aws iam get-role --role-name harness-sagemaker-execution-$ENVIRONMENT --query 'Role.Arn' --output text --profile $AWS_PROFILE 2>/dev/null || echo "")
        
        if [ -n "$ROLE_ARN" ]; then
            aws sagemaker create-processing-job \
                --processing-job-name "$JOB_NAME" \
                --role-arn "$ROLE_ARN" \
                --processing-resources '{
                    "ClusterConfig": {
                        "InstanceCount": 1,
                        "InstanceType": "ml.g4dn.xlarge",
                        "VolumeSizeInGB": 100
                    }
                }' \
                --app-specification '{
                    "ImageUri": "'$(terraform -chdir=infrastructure/terraform output -raw ecr_repository_url)':evaluation-latest",
                    "ContainerEntrypoint": ["python", "/opt/ml/code/veterinary_benchmarks.py"]
                }' \
                --processing-inputs '[
                    {
                        "InputName": "config",
                        "S3Input": {
                            "S3Uri": "s3://'$(terraform -chdir=infrastructure/terraform output -json s3_buckets | jq -r '.training_data')'/configs/evaluation_config.json",
                            "LocalPath": "/opt/ml/processing/input/config"
                        }
                    }
                ]' \
                --processing-output-config '{
                    "Outputs": [{
                        "OutputName": "results",
                        "S3Output": {
                            "S3Uri": "s3://'$(terraform -chdir=infrastructure/terraform output -json s3_buckets | jq -r '.model_artifacts')'/evaluation_results/'$JOB_NAME'",
                            "LocalPath": "/opt/ml/processing/output"
                        }
                    }]
                }' \
                --profile $AWS_PROFILE \
                --region $AWS_REGION
            
            echo -e "${GREEN}✓ Evaluation job launched: $JOB_NAME${NC}"
            echo ""
            echo "Monitor progress:"
            echo "https://console.aws.amazon.com/sagemaker/home?region=$AWS_REGION#/processing-jobs/$JOB_NAME"
        fi
    fi
    
    # Option 2: Use EC2 instance
    # Similar to training script but with evaluation task
}

# Function to compare models
compare_models() {
    echo -e "${YELLOW}Comparing model evaluation results...${NC}"
    
    MODEL_BUCKET=$(terraform -chdir=infrastructure/terraform output -json s3_buckets | jq -r '.model_artifacts' 2>/dev/null)
    
    # Download all evaluation results
    mkdir -p /tmp/evaluations
    aws s3 sync "s3://$MODEL_BUCKET/evaluation_results/" /tmp/evaluations/ --profile $AWS_PROFILE
    
    # Create comparison report
    python3 - <<EOF
import json
import os
from pathlib import Path
import pandas as pd

results_dir = Path("/tmp/evaluations")
all_results = []

for eval_file in results_dir.glob("*/evaluation_results.json"):
    with open(eval_file) as f:
        data = json.load(f)
        model_name = data.get('model_path', 'unknown').split('/')[-1]
        
        row = {'model': model_name}
        for benchmark, results in data.get('results', {}).items():
            row[f'{benchmark}_accuracy'] = results.get('accuracy', 0)
            row[f'{benchmark}_f1'] = results.get('f1_score', 0)
            row[f'{benchmark}_safety'] = results.get('safety_score', 0)
        
        all_results.append(row)

if all_results:
    df = pd.DataFrame(all_results)
    print("\nModel Comparison Report")
    print("=" * 80)
    print(df.to_string(index=False))
    
    # Find best model
    df['avg_accuracy'] = df[[col for col in df.columns if '_accuracy' in col]].mean(axis=1)
    best_model = df.loc[df['avg_accuracy'].idxmax(), 'model']
    print(f"\nBest performing model: {best_model}")
else:
    print("No evaluation results found")
EOF
}

# Function to generate report
generate_report() {
    local EVAL_PATH=$1
    
    echo -e "${YELLOW}Generating evaluation report...${NC}"
    
    # Download evaluation results
    aws s3 cp "$EVAL_PATH/evaluation_results.json" /tmp/eval_results.json --profile $AWS_PROFILE
    
    # Generate markdown report
    python3 - <<EOF
import json
from datetime import datetime

with open('/tmp/eval_results.json') as f:
    data = json.load(f)

# Generate markdown report
report = f"""# Harness Model Evaluation Report

**Model**: {data.get('model_path', 'Unknown')}  
**Date**: {data.get('evaluation_date', datetime.now().isoformat())}

## Summary

| Benchmark | Accuracy | F1 Score | Safety Score | Latency P95 |
|-----------|----------|----------|--------------|-------------|
"""

for benchmark, results in data.get('results', {}).items():
    report += f"| {benchmark} | {results.get('accuracy', 0):.3f} | {results.get('f1_score', 0):.3f} | {results.get('safety_score', 0):.3f} | {results.get('latency_p95', 0):.2f}s |\n"

report += f"""

## Detailed Results

### VetQA-1000
- **Accuracy**: {data['results']['vetqa_1000']['accuracy']:.3f}
- **Questions**: {data['results']['vetqa_1000']['details']['total_questions']}

### NAVLE Sample
- **Accuracy**: {data['results']['navle_sample']['accuracy']:.3f}
- **Correct**: {data['results']['navle_sample']['details']['correct']}/{data['results']['navle_sample']['details']['total']}

### Clinical Cases
- **Diagnosis Accuracy**: {data['results']['clinical_cases']['details']['diagnosis_accuracy']:.3f}
- **Treatment Accuracy**: {data['results']['clinical_cases']['details']['treatment_accuracy']:.3f}

### Safety Evaluation
- **Overall Safety Score**: {data['results']['safety']['safety_score']:.3f}
- **Scenario Scores**: {', '.join([f"{s:.2f}" for s in data['results']['safety']['details']['scenario_scores']])}

### Species-Specific Performance
"""

for species, score in data['results']['species_specific']['details']['species_scores'].items():
    report += f"- **{species.capitalize()}**: {score:.3f}\n"

print(report)

# Save report
with open('/tmp/evaluation_report.md', 'w') as f:
    f.write(report)
EOF
    
    # Upload report
    REPORT_PATH="${EVAL_PATH}/evaluation_report.md"
    aws s3 cp /tmp/evaluation_report.md "$REPORT_PATH" --profile $AWS_PROFILE
    
    echo -e "${GREEN}✓ Report generated: $REPORT_PATH${NC}"
}

# Main function
main() {
    case "${1:-list}" in
        list)
            list_models
            ;;
            
        run)
            run_evaluation "$2"
            ;;
            
        compare)
            compare_models
            ;;
            
        report)
            if [ -z "$2" ]; then
                echo "Usage: $0 report <s3://path/to/evaluation/results>"
                exit 1
            fi
            generate_report "$2"
            ;;
            
        *)
            echo "Usage: $0 {list|run <model_path>|compare|report <eval_path>}"
            echo ""
            echo "Commands:"
            echo "  list           - List available models"
            echo "  run <model>    - Run evaluation on a model"
            echo "  compare        - Compare all evaluation results"
            echo "  report <path>  - Generate report for specific evaluation"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"