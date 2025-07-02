# RDS PostgreSQL for Harness API
resource "aws_db_subnet_group" "harness" {
  name       = "${var.project_name}-db-subnet-${var.environment}"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "${var.project_name}-db-subnet-${var.environment}"
  }
}

resource "aws_security_group" "harness_db" {
  name        = "${var.project_name}-db-sg-${var.environment}"
  description = "Security group for Harness RDS"
  vpc_id      = aws_vpc.harness.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-db-sg-${var.environment}"
  }
}

resource "aws_db_instance" "harness" {
  identifier     = "${var.project_name}-db-${var.environment}"
  engine         = "postgres"
  engine_version = "16.4"
  instance_class = "db.t3.medium"
  
  allocated_storage     = 100
  storage_type         = "gp3"
  storage_encrypted    = true
  
  db_name  = "harness"
  username = "harness"
  password = random_password.harness_db.result
  
  vpc_security_group_ids = [aws_security_group.harness_db.id]
  db_subnet_group_name   = aws_db_subnet_group.harness.name
  
  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "sun:04:00-sun:05:00"
  
  skip_final_snapshot = true
  deletion_protection = false

  tags = {
    Name = "${var.project_name}-db-${var.environment}"
  }
}

resource "random_password" "harness_db" {
  length           = 32
  special          = true
  override_special = "!#$%&*()_+-=[]{}|;:,.<>?"
}

# ElastiCache Redis for caching
resource "aws_elasticache_subnet_group" "harness" {
  name       = "${var.project_name}-cache-subnet-${var.environment}"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "${var.project_name}-cache-subnet-${var.environment}"
  }
}

resource "aws_security_group" "harness_cache" {
  name        = "${var.project_name}-cache-sg-${var.environment}"
  description = "Security group for Harness ElastiCache"
  vpc_id      = aws_vpc.harness.id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-cache-sg-${var.environment}"
  }
}

resource "aws_elasticache_cluster" "harness" {
  cluster_id           = "${var.project_name}-cache-${var.environment}"
  engine               = "redis"
  node_type            = "cache.t3.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  engine_version       = "7.1"
  port                 = 6379
  
  subnet_group_name = aws_elasticache_subnet_group.harness.name
  security_group_ids = [aws_security_group.harness_cache.id]

  tags = {
    Name = "${var.project_name}-cache-${var.environment}"
  }
}

# Outputs
output "database_endpoint" {
  description = "RDS database endpoint"
  value       = aws_db_instance.harness.endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "Redis cache endpoint"
  value       = aws_elasticache_cluster.harness.cache_nodes[0].address
}