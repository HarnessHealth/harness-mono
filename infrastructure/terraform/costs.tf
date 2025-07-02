# Cost Management and Budgets

# Enable Cost Explorer
resource "aws_ce_cost_category" "harness" {
  name         = "harness-cost-categories"
  rule_version = "CostCategoryExpression.v1"

  rule {
    value = "Compute"
    rule {
      dimension {
        key    = "SERVICE_CODE"
        values = ["AmazonEC2", "AmazonECS", "AWSLambda"]
      }
    }
  }

  rule {
    value = "Storage"
    rule {
      dimension {
        key    = "SERVICE_CODE"
        values = ["AmazonS3", "AmazonEBS"]
      }
    }
  }

  rule {
    value = "Database"
    rule {
      dimension {
        key    = "SERVICE_CODE"
        values = ["AmazonRDS", "AmazonElastiCache"]
      }
    }
  }

  rule {
    value = "ML"
    rule {
      dimension {
        key    = "SERVICE_CODE"
        values = ["AmazonSageMaker", "AmazonBedrock"]
      }
    }
  }

  rule {
    value = "Other"
    type  = "REGULAR"
    rule {
      dimension {
        key    = "SERVICE_CODE"
        values = ["AmazonVPC", "AmazonRoute53", "AmazonCloudWatch"]
      }
    }
  }
}

# Monthly Budget with Alerts
resource "aws_budgets_budget" "monthly" {
  name         = "${var.project_name}-monthly-budget"
  budget_type  = "COST"
  limit_amount = "5000"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["Project$Harness"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_email_addresses = [var.admin_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_email_addresses = [var.admin_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 120
    threshold_type            = "PERCENTAGE"
    notification_type         = "FORECASTED"
    subscriber_email_addresses = [var.admin_email]
  }
}

# Budget for specific services
resource "aws_budgets_budget" "sagemaker" {
  name         = "${var.project_name}-sagemaker-budget"
  budget_type  = "COST"
  limit_amount = "1500"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "Service"
    values = ["Amazon SageMaker"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 90
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_email_addresses = [var.admin_email]
  }
}

# Training-specific budget (strict $50 limit)
resource "aws_budgets_budget" "training" {
  name         = "${var.project_name}-training-budget"
  budget_type  = "COST"
  limit_amount = "50"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "Service"
    values = ["Amazon Elastic Compute Cloud - Compute"]
  }

  cost_filter {
    name   = "TagKeyValue"
    values = ["Type$training"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type            = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.admin_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type            = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.admin_email]
  }
}

# Cost Anomaly Detector
resource "aws_ce_anomaly_monitor" "harness" {
  name         = "${var.project_name}-anomaly-monitor"
  monitor_type = "CUSTOM"

  monitor_specification = jsonencode({
    Tags = {
      Key    = "Project"
      Values = ["Harness"]
    }
  })
}

resource "aws_ce_anomaly_subscription" "harness" {
  name      = "${var.project_name}-anomaly-subscription"
  frequency = "DAILY"

  threshold_expression {
    dimension {
      key           = "ANOMALY_TOTAL_IMPACT_ABSOLUTE"
      values        = ["100"]
      match_options = ["GREATER_THAN_OR_EQUAL"]
    }
  }

  monitor_arn_list = [
    aws_ce_anomaly_monitor.harness.arn,
  ]

  subscriber {
    type    = "EMAIL"
    address = var.admin_email
  }
}

# IAM Role for Cost Explorer API Access
resource "aws_iam_role_policy" "cost_explorer_access" {
  name = "${var.project_name}-cost-explorer-policy"
  role = aws_iam_role.api_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ce:GetCostAndUsage",
          "ce:GetCostForecast",
          "ce:GetReservationUtilization",
          "ce:GetDimensionValues",
          "ce:GetTags",
          "ce:GetAnomalies",
          "ce:GetAnomalyMonitors",
          "ce:GetAnomalySubscriptions",
          "budgets:ViewBudget",
          "budgets:DescribeBudget",
          "budgets:DescribeBudgetPerformanceHistory"
        ]
        Resource = "*"
      }
    ]
  })
}

# Output budget information
output "monthly_budget_name" {
  description = "Name of the monthly budget"
  value       = aws_budgets_budget.monthly.name
}

output "cost_category_arn" {
  description = "ARN of the cost category"
  value       = aws_ce_cost_category.harness.arn
}

# Variables for cost management
variable "admin_email" {
  description = "Admin email for budget alerts"
  type        = string
  default     = "admin@harness.health"
}