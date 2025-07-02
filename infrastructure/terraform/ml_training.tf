# EC2 Launch Template for GPU Training
resource "aws_launch_template" "gpu_training" {
  name_prefix   = "${var.project_name}-gpu-training-"
  image_id      = data.aws_ami.deep_learning.id
  instance_type = var.gpu_instance_type

  vpc_security_group_ids = [aws_security_group.gpu_training.id]

  iam_instance_profile {
    name = aws_iam_instance_profile.gpu_training.name
  }

  block_device_mappings {
    device_name = "/dev/sda1"

    ebs {
      volume_size = 2000
      volume_type = "gp3"
      iops        = 16000
      throughput  = 1000
      encrypted   = true
    }
  }

  user_data = base64encode(templatefile("${path.module}/scripts/gpu_training_init.sh", {
    s3_model_bucket    = aws_s3_bucket.model_artifacts.id
    s3_training_bucket = aws_s3_bucket.training_data.id
    project_name       = var.project_name
    aws_region         = var.aws_region
    wandb_api_key      = var.wandb_api_key
  }))

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "${var.project_name}-gpu-training-${var.environment}"
      Type = "training"
    }
  }

  tag_specifications {
    resource_type = "volume"
    tags = {
      Name = "${var.project_name}-gpu-training-volume-${var.environment}"
    }
  }
}

# Get latest Deep Learning AMI
data "aws_ami" "deep_learning" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["Deep Learning AMI GPU PyTorch 2.* (Ubuntu 20.04)*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Auto Scaling Group for GPU Training (Spot Instances)
resource "aws_autoscaling_group" "gpu_training" {
  name                = "${var.project_name}-gpu-training-asg-${var.environment}"
  vpc_zone_identifier = aws_subnet.private[*].id
  min_size            = 0
  max_size            = 4
  desired_capacity    = 0

  mixed_instances_policy {
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.gpu_training.id
        version           = "$Latest"
      }

      override {
        instance_type = "p4d.24xlarge"
        weighted_capacity = 8
      }

      override {
        instance_type = "p3dn.24xlarge"
        weighted_capacity = 8
      }
    }

    instances_distribution {
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "capacity-optimized"
    }
  }

  tag {
    key                 = "Name"
    value               = "${var.project_name}-gpu-training-${var.environment}"
    propagate_at_launch = true
  }
}

# SageMaker for managed training jobs
resource "aws_sagemaker_domain" "harness" {
  domain_name = "${var.project_name}-ml-${var.environment}"
  auth_mode   = "IAM"
  vpc_id      = aws_vpc.harness.id
  subnet_ids  = aws_subnet.private[*].id

  default_user_settings {
    execution_role = aws_iam_role.sagemaker_execution.arn

    jupyter_server_app_settings {
      default_resource_spec {
        instance_type = "system"
      }
    }

    kernel_gateway_app_settings {
      default_resource_spec {
        instance_type = "ml.t3.medium"
      }
    }
  }

  tags = {
    Name = "${var.project_name}-ml-domain-${var.environment}"
  }
}

# IAM Role for SageMaker
resource "aws_iam_role" "sagemaker_execution" {
  name = "${var.project_name}-sagemaker-execution-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "sagemaker.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-sagemaker-execution-${var.environment}"
  }
}

# IAM Policy for SageMaker
resource "aws_iam_role_policy_attachment" "sagemaker_full_access" {
  role       = aws_iam_role.sagemaker_execution.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess"
}

resource "aws_iam_role_policy" "sagemaker_s3_access" {
  name = "${var.project_name}-sagemaker-s3-policy-${var.environment}"
  role = aws_iam_role.sagemaker_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.model_artifacts.arn,
          "${aws_s3_bucket.model_artifacts.arn}/*",
          aws_s3_bucket.training_data.arn,
          "${aws_s3_bucket.training_data.arn}/*"
        ]
      }
    ]
  })
}

# ECR Repository for training containers
resource "aws_ecr_repository" "training" {
  name                 = "${var.project_name}-training-${var.environment}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name = "${var.project_name}-training-ecr-${var.environment}"
  }
}

# IAM Instance Profile for GPU instances
resource "aws_iam_instance_profile" "gpu_training" {
  name = "${var.project_name}-gpu-training-profile-${var.environment}"
  role = aws_iam_role.gpu_training.name
}

resource "aws_iam_role" "gpu_training" {
  name = "${var.project_name}-gpu-training-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-gpu-training-role-${var.environment}"
  }
}

resource "aws_iam_role_policy" "gpu_training" {
  name = "${var.project_name}-gpu-training-policy-${var.environment}"
  role = aws_iam_role.gpu_training.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.model_artifacts.arn,
          "${aws_s3_bucket.model_artifacts.arn}/*",
          aws_s3_bucket.training_data.arn,
          "${aws_s3_bucket.training_data.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# CloudWatch Log Group for training
resource "aws_cloudwatch_log_group" "training" {
  name              = "/aws/harness/training/${var.environment}"
  retention_in_days = 30

  tags = {
    Name = "${var.project_name}-training-logs-${var.environment}"
  }
}