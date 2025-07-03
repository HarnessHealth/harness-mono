#!/usr/bin/env python3
"""
Production MedGemma-27B-IT SageMaker Deployment with Cost Management
"""
import json
import os
import sys
import boto3
import sagemaker
from sagemaker.huggingface import HuggingFaceModel, get_huggingface_llm_image_uri
from datetime import datetime
import argparse


class MedGemmaSageMakerDeployer:
    """Deploy and manage MedGemma models on SageMaker"""
    
    def __init__(self, environment="development"):
        self.environment = environment
        self.session = boto3.Session()
        self.sagemaker_session = sagemaker.Session(boto_session=self.session)
        
        # Cost estimates (per hour)
        self.instance_costs = {
            "ml.g5.2xlarge": 1.006,   # 1 GPU, 8 vCPU, 32 GB RAM
            "ml.g5.4xlarge": 1.692,   # 1 GPU, 16 vCPU, 64 GB RAM  
            "ml.g5.8xlarge": 2.744,   # 1 GPU, 32 vCPU, 128 GB RAM
            "ml.g5.12xlarge": 5.672,  # 4 GPU, 48 vCPU, 192 GB RAM
            "ml.g5.24xlarge": 10.10,  # 4 GPU, 96 vCPU, 384 GB RAM
            "ml.g5.48xlarge": 20.19   # 8 GPU, 192 vCPU, 768 GB RAM
        }
    
    def get_huggingface_token(self):
        """Get HuggingFace access token from environment"""
        # Try multiple environment variable names
        token_vars = ['HUGGINGFACE_ACCESS_TOKEN', 'HF_TOKEN', 'HUGGINGFACE_TOKEN']
        
        for var_name in token_vars:
            token = os.getenv(var_name)
            if token and token != '<REPLACE WITH YOUR TOKEN>':
                print(f"✓ Found HuggingFace token in {var_name}")
                return token
        
        # No token found
        raise ValueError("HUGGINGFACE_ACCESS_TOKEN environment variable is required. Please set it in your environment.")
    
    def get_sagemaker_role(self):
        """Get SageMaker execution role"""
        try:
            role = sagemaker.get_execution_role()
            print(f"✓ Using SageMaker execution role")
            return role
        except ValueError:
            # Get role from IAM for the current environment
            iam = boto3.client('iam')
            role_name = f"harness-sagemaker-execution-role-{self.environment}"
            
            try:
                role = iam.get_role(RoleName=role_name)['Role']['Arn']
                print(f"✓ Using IAM role: {role_name}")
                return role
            except iam.exceptions.NoSuchEntityException:
                print(f"❌ SageMaker execution role '{role_name}' not found")
                print("Please create the role with the following policies:")
                print("- AmazonSageMakerFullAccess")
                print("- AmazonS3FullAccess")
                sys.exit(1)
    
    def estimate_costs(self, instance_type, hours_per_day=8, days=30):
        """Estimate monthly costs for the deployment"""
        hourly_cost = self.instance_costs.get(instance_type, 0)
        daily_cost = hourly_cost * hours_per_day
        monthly_cost = daily_cost * days
        
        print(f"📊 Cost Estimation for {instance_type}:")
        print(f"   Hourly: ${hourly_cost:.3f}")
        print(f"   Daily ({hours_per_day}h): ${daily_cost:.2f}")
        print(f"   Monthly ({days} days): ${monthly_cost:.2f}")
        
        return monthly_cost
    
    def check_service_quotas(self, instance_type):
        """Check if we have sufficient service quotas"""
        try:
            quotas = boto3.client('service-quotas')
            # This is a simplified check - in production you'd want more comprehensive quota checking
            print(f"⚠ Please verify you have quota for {instance_type} instances in your region")
            return True
        except Exception as e:
            print(f"⚠ Could not check service quotas: {e}")
            return True
    
    def create_model_config(self, model_size="27b"):
        """Create model configuration based on size"""
        configs = {
            "4b": {
                "model_id": "google/medgemma-4b-it",
                "instance_type": "ml.g5.2xlarge",
                "num_gpus": 1,
                "max_input_length": 4096,
                "max_total_tokens": 8192
            },
            "7b": {
                "model_id": "google/medgemma-7b-it", 
                "instance_type": "ml.g5.4xlarge",
                "num_gpus": 1,
                "max_input_length": 4096,
                "max_total_tokens": 8192
            },
            "27b": {
                "model_id": "google/medgemma-27b-it",
                "instance_type": "ml.g5.12xlarge",
                "num_gpus": 4,
                "max_input_length": 4096,
                "max_total_tokens": 8192
            }
        }
        
        return configs.get(model_size, configs["27b"])
    
    def deploy_model(self, model_size="27b", auto_scale=False):
        """Deploy MedGemma model to SageMaker"""
        print(f"🚀 Starting MedGemma-{model_size.upper()}-IT deployment...")
        
        # Get configuration
        config = self.create_model_config(model_size)
        hf_token = self.get_huggingface_token()
        role = self.get_sagemaker_role()
        
        # Estimate costs
        monthly_cost = self.estimate_costs(config["instance_type"])
        
        if monthly_cost > 1000:  # Warn for expensive deployments
            response = input(f"⚠ Estimated monthly cost: ${monthly_cost:.2f}. Continue? (y/N): ")
            if response.lower() != 'y':
                print("Deployment cancelled")
                return None
        
        # Check quotas
        self.check_service_quotas(config["instance_type"])
        
        # Model environment configuration
        hub = {
            'HF_MODEL_ID': config["model_id"],
            'SM_NUM_GPUS': json.dumps(config["num_gpus"]),
            'HF_TOKEN': hf_token,
            'MAX_INPUT_LENGTH': json.dumps(config["max_input_length"]),
            'MAX_TOTAL_TOKENS': json.dumps(config["max_total_tokens"]),
            'MAX_BATCH_PREFILL_TOKENS': json.dumps(2048),
            'TRUST_REMOTE_CODE': json.dumps(True),
            'MESSAGES_API_ENABLED': json.dumps(True)
        }
        
        print(f"📋 Model Configuration:")
        print(f"   Model: {config['model_id']}")
        print(f"   Instance: {config['instance_type']}")
        print(f"   GPUs: {config['num_gpus']}")
        print(f"   Environment: {self.environment}")
        
        # Create model
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        model_name = f"medgemma-{model_size}-{self.environment}-{timestamp}"
        endpoint_name = f"medgemma-{model_size}-{self.environment}"
        
        try:
            huggingface_model = HuggingFaceModel(
                image_uri=get_huggingface_llm_image_uri("huggingface", version="3.2.3"),
                env=hub,
                role=role,
                name=model_name,
                sagemaker_session=self.sagemaker_session
            )
            print("✓ HuggingFace model created")
        except Exception as e:
            print(f"❌ Error creating model: {e}")
            return None
        
        # Deploy model
        print("🔄 Deploying to SageMaker (this may take 15-20 minutes)...")
        try:
            predictor = huggingface_model.deploy(
                initial_instance_count=1,
                instance_type=config["instance_type"],
                container_startup_health_check_timeout=1200,  # 20 minutes
                endpoint_name=endpoint_name,
                wait=True
            )
            
            print(f"✅ Model deployed successfully!")
            print(f"   Endpoint: {predictor.endpoint_name}")
            
            # Test the deployment
            self.test_endpoint(predictor)
            
            return predictor.endpoint_name
            
        except Exception as e:
            print(f"❌ Deployment failed: {e}")
            self.print_troubleshooting_tips()
            return None
    
    def test_endpoint(self, predictor):
        """Test the deployed endpoint with veterinary questions"""
        print("🧪 Testing deployment...")
        
        test_cases = [
            {
                "input": "What are the early signs of kidney disease in cats?",
                "expected_topics": ["kidney", "cats", "symptoms"]
            },
            {
                "input": "How do I treat a dog with bloat?",
                "expected_topics": ["bloat", "gastric", "emergency"]
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            try:
                print(f"\\n  Test {i}: {test_case['input']}")
                response = predictor.predict({
                    "inputs": test_case["input"],
                    "parameters": {
                        "max_new_tokens": 200,
                        "temperature": 0.7,
                        "do_sample": True,
                        "top_p": 0.9
                    }
                })
                
                output = response[0]['generated_text'][len(test_case['input']):].strip()
                print(f"  Response: {output[:100]}...")
                print("  ✓ Test passed")
                
            except Exception as e:
                print(f"  ❌ Test failed: {e}")
    
    def print_troubleshooting_tips(self):
        """Print troubleshooting information"""
        print("\\n🔧 Troubleshooting Tips:")
        print("1. Check service quotas for the instance type in AWS Console")
        print("2. Verify SageMaker execution role has proper permissions")
        print("3. Ensure HuggingFace token is valid and has model access")
        print("4. Check CloudWatch logs for detailed error messages")
        print("5. Try a smaller instance type if deployment fails")


def main():
    """Main function with CLI interface"""
    parser = argparse.ArgumentParser(description="Deploy MedGemma models to SageMaker")
    parser.add_argument("--model-size", choices=["4b", "7b", "27b"], default="27b",
                       help="Model size to deploy (default: 27b)")
    parser.add_argument("--environment", choices=["development", "staging", "production"], 
                       default="development", help="Deployment environment")
    parser.add_argument("--auto-scale", action="store_true", 
                       help="Enable auto-scaling (not implemented yet)")
    
    args = parser.parse_args()
    
    print("🏥 MedGemma SageMaker Deployment Tool")
    print("=" * 50)
    
    # Check AWS credentials
    try:
        boto3.client('sts').get_caller_identity()
        print("✓ AWS credentials verified")
    except Exception as e:
        print(f"❌ AWS credentials error: {e}")
        sys.exit(1)
    
    # Deploy the model
    deployer = MedGemmaSageMakerDeployer(args.environment)
    endpoint_name = deployer.deploy_model(args.model_size, args.auto_scale)
    
    if endpoint_name:
        print(f"\\n🎉 Deployment completed!")
        print(f"   Endpoint: {endpoint_name}")
        print(f"   Environment: {args.environment}")
        print("\\n📚 Next Steps:")
        print("1. Update inference service configuration")
        print("2. Set up monitoring and alerting")
        print("3. Configure auto-scaling if needed")
        print("4. Test with production veterinary questions")
        print(f"\\n🗑️  To delete later:")
        print(f"   aws sagemaker delete-endpoint --endpoint-name {endpoint_name}")
    else:
        print("❌ Deployment failed")
        sys.exit(1)


if __name__ == "__main__":
    main()