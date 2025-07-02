# AWS CodeBuild for Docker image builds

# S3 bucket for CodeBuild artifacts and cache
resource "aws_s3_bucket" "codebuild_cache" {
  bucket = "${var.project_name}-codebuild-cache-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_lifecycle_configuration" "codebuild_cache" {
  bucket = aws_s3_bucket.codebuild_cache.id

  rule {
    id     = "expire-old-cache"
    status = "Enabled"

    filter {}

    expiration {
      days = 7
    }
  }
}

# IAM role for CodeBuild
resource "aws_iam_role" "codebuild" {
  name = "${var.project_name}-codebuild-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "codebuild.amazonaws.com"
        }
      }
    ]
  })
}

# IAM policy for CodeBuild
resource "aws_iam_role_policy" "codebuild" {
  name = "${var.project_name}-codebuild-policy"
  role = aws_iam_role.codebuild.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.codebuild_cache.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "codecommit:GitPull"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecs:UpdateService",
          "ecs:DescribeServices",
          "ecs:DescribeClusters"
        ]
        Resource = [
          "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:cluster/${var.project_name}-*",
          "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:service/${var.project_name}-*/*"
        ]
      }
    ]
  })
}

# CodeBuild project for backend
resource "aws_codebuild_project" "backend" {
  name          = "${var.project_name}-backend-build"
  description   = "Build backend Docker image"
  service_role  = aws_iam_role.codebuild.arn

  artifacts {
    type = "NO_ARTIFACTS"
  }

  cache {
    type     = "S3"
    location = "${aws_s3_bucket.codebuild_cache.bucket}/backend"
    modes    = ["LOCAL_DOCKER_LAYER_CACHE", "LOCAL_SOURCE_CACHE"]
  }

  environment {
    compute_type                = "BUILD_GENERAL1_MEDIUM"
    image                      = "aws/codebuild/standard:7.0"
    type                       = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
    privileged_mode            = true

    environment_variable {
      name  = "AWS_DEFAULT_REGION"
      value = var.aws_region
    }

    environment_variable {
      name  = "AWS_ACCOUNT_ID"
      value = data.aws_caller_identity.current.account_id
    }

    environment_variable {
      name  = "ECR_REPOSITORY_URI"
      value = aws_ecr_repository.api.repository_url
    }

    environment_variable {
      name  = "IMAGE_TAG"
      value = "latest"
    }
  }

  source {
    type            = "GITHUB"
    location        = "https://github.com/HarnessHealth/harness-mono.git"
    git_clone_depth = 1
    git_submodules_config {
      fetch_submodules = false
    }
    buildspec = file("${path.module}/buildspecs/backend-buildspec.yml")
  }

  logs_config {
    cloudwatch_logs {
      group_name  = "/aws/codebuild/${var.project_name}-backend"
      stream_name = ""
    }
  }

  tags = {
    Name = "${var.project_name}-backend-build"
  }
}

# GitHub webhook for backend builds
resource "aws_codebuild_webhook" "backend" {
  project_name = aws_codebuild_project.backend.name
  build_type   = "BUILD"

  filter_group {
    filter {
      type    = "EVENT"
      pattern = "PUSH"
    }

    filter {
      type    = "HEAD_REF"
      pattern = "refs/heads/master"
    }
  }
}

# CodeBuild project for Lambda functions
resource "aws_codebuild_project" "lambda" {
  name          = "${var.project_name}-lambda-build"
  description   = "Build Lambda function Docker images"
  service_role  = aws_iam_role.codebuild.arn

  artifacts {
    type = "NO_ARTIFACTS"
  }

  cache {
    type     = "S3"
    location = "${aws_s3_bucket.codebuild_cache.bucket}/lambda"
    modes    = ["LOCAL_DOCKER_LAYER_CACHE", "LOCAL_SOURCE_CACHE"]
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                      = "aws/codebuild/standard:7.0"
    type                       = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
    privileged_mode            = true

    environment_variable {
      name  = "AWS_DEFAULT_REGION"
      value = var.aws_region
    }

    environment_variable {
      name  = "AWS_ACCOUNT_ID"
      value = data.aws_caller_identity.current.account_id
    }

    environment_variable {
      name  = "ECR_REPOSITORY_URI"
      value = aws_ecr_repository.api.repository_url
    }
  }

  source {
    type            = "GITHUB"
    location        = "https://github.com/HarnessHealth/harness-mono.git"
    git_clone_depth = 1
    git_submodules_config {
      fetch_submodules = false
    }
    buildspec = file("${path.module}/buildspecs/lambda-buildspec.yml")
  }

  logs_config {
    cloudwatch_logs {
      group_name  = "/aws/codebuild/${var.project_name}-lambda"
      stream_name = ""
    }
  }

  tags = {
    Name = "${var.project_name}-lambda-build"
  }
}

# GitHub webhook for lambda builds
resource "aws_codebuild_webhook" "lambda" {
  project_name = aws_codebuild_project.lambda.name
  build_type   = "BUILD"

  filter_group {
    filter {
      type    = "EVENT"
      pattern = "PUSH"
    }

    filter {
      type    = "HEAD_REF"
      pattern = "refs/heads/master"
    }

    filter {
      type    = "FILE_PATH"
      pattern = "data-pipeline/lambdas/**/*"
    }
  }
}

# CodeBuild project for admin frontend
resource "aws_codebuild_project" "admin" {
  name          = "${var.project_name}-admin-build"
  description   = "Build admin frontend Docker image"
  service_role  = aws_iam_role.codebuild.arn

  artifacts {
    type = "NO_ARTIFACTS"
  }

  cache {
    type     = "S3"
    location = "${aws_s3_bucket.codebuild_cache.bucket}/admin"
    modes    = ["LOCAL_DOCKER_LAYER_CACHE", "LOCAL_SOURCE_CACHE"]
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                      = "aws/codebuild/standard:7.0"
    type                       = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
    privileged_mode            = true

    environment_variable {
      name  = "AWS_DEFAULT_REGION"
      value = var.aws_region
    }

    environment_variable {
      name  = "AWS_ACCOUNT_ID"
      value = data.aws_caller_identity.current.account_id
    }

    environment_variable {
      name  = "ECR_REPOSITORY_URI"
      value = aws_ecr_repository.admin.repository_url
    }

    environment_variable {
      name  = "IMAGE_TAG"
      value = "latest"
    }

    environment_variable {
      name  = "VITE_API_URL"
      value = "https://api.${var.domain_name}"
    }
  }

  source {
    type            = "GITHUB"
    location        = "https://github.com/HarnessHealth/harness-mono.git"
    git_clone_depth = 1
    git_submodules_config {
      fetch_submodules = false
    }
    buildspec = file("${path.module}/buildspecs/admin-buildspec.yml")
  }

  logs_config {
    cloudwatch_logs {
      group_name  = "/aws/codebuild/${var.project_name}-admin"
      stream_name = ""
    }
  }

  tags = {
    Name = "${var.project_name}-admin-build"
  }
}

# GitHub webhook for admin builds
resource "aws_codebuild_webhook" "admin" {
  project_name = aws_codebuild_project.admin.name
  build_type   = "BUILD"

  filter_group {
    filter {
      type    = "EVENT"
      pattern = "PUSH"
    }

    filter {
      type    = "HEAD_REF"
      pattern = "refs/heads/master"
    }

    filter {
      type    = "FILE_PATH"
      pattern = "admin-frontend/**/*"
    }
  }
}

# SNS topic for build notifications
resource "aws_sns_topic" "codebuild_notifications" {
  name = "${var.project_name}-codebuild-notifications"
}

resource "aws_sns_topic_subscription" "codebuild_email" {
  topic_arn = aws_sns_topic.codebuild_notifications.arn
  protocol  = "email"
  endpoint  = var.admin_email
}

# CloudWatch Event Rule for build status
resource "aws_cloudwatch_event_rule" "codebuild_status" {
  name        = "${var.project_name}-codebuild-status"
  description = "Capture CodeBuild build status changes"

  event_pattern = jsonencode({
    source      = ["aws.codebuild"]
    detail-type = ["CodeBuild Build State Change"]
    detail = {
      project-name = [
        aws_codebuild_project.backend.name,
        aws_codebuild_project.lambda.name,
        aws_codebuild_project.admin.name
      ]
      build-status = ["FAILED", "SUCCEEDED"]
    }
  })
}

resource "aws_cloudwatch_event_target" "sns" {
  rule      = aws_cloudwatch_event_rule.codebuild_status.name
  target_id = "SendToSNS"
  arn       = aws_sns_topic.codebuild_notifications.arn
}

# Output build project names
output "codebuild_backend_project" {
  description = "CodeBuild project name for backend"
  value       = aws_codebuild_project.backend.name
}

output "codebuild_lambda_project" {
  description = "CodeBuild project name for Lambda functions"
  value       = aws_codebuild_project.lambda.name
}

output "codebuild_admin_project" {
  description = "CodeBuild project name for admin frontend"
  value       = aws_codebuild_project.admin.name
}