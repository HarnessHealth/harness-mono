variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "development"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "harness"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones"
  type        = list(string)
  default     = ["us-east-1b", "us-east-1c", "us-east-1d"] # Avoid us-east-1a for GPU instances
}

variable "gpu_instance_type" {
  description = "EC2 instance type for GPU training"
  type        = string
  default     = "g4dn.xlarge" # 1x T4 GPU, 4 vCPUs - Good for development
  # Other options:
  # "g4dn.2xlarge"  # 1x T4 GPU, 8 vCPUs
  # "p3.2xlarge"    # 1x V100 GPU, 8 vCPUs  
  # "p4d.24xlarge"  # 8x A100 GPUs, 96 vCPUs (requires quota increase)
}

variable "airflow_instance_type" {
  description = "EC2 instance type for Airflow"
  type        = string
  default     = "t3.xlarge"
}

variable "weaviate_instance_type" {
  description = "EC2 instance type for Weaviate"
  type        = string
  default     = "r6i.2xlarge" # Memory optimized for vector DB
}

variable "wandb_api_key" {
  description = "Weights & Biases API key for experiment tracking (optional)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = "harness.health"
}