terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket = "harness-terraform-state-285641110801"
    key    = "harness/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "Harness"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# Data source for current AWS account ID
data "aws_caller_identity" "current" {}