# Finance A2A Automation - Terraform Configuration
# This configuration deploys the complete infrastructure on AWS

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Variables
variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "finance-a2a"
}

variable "db_password" {
  description = "Database master password"
  type        = string
  sensitive   = true
}

variable "google_api_key" {
  description = "Google API Key for Gemini"
  type        = string
  sensitive   = true
}

variable "perplexity_api_key" {
  description = "Perplexity API Key"
  type        = string
  sensitive   = true
}

variable "firebase_project_id" {
  description = "Firebase Project ID"
  type        = string
}

variable "bastion_public_key" {
  description = "SSH public key for bastion host access"
  type        = string
}

# VPC
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

# Internet Gateway
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-igw"
  }
}

# Public Subnets
resource "aws_subnet" "public_1" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-1a"
  }
}

resource "aws_subnet" "public_2" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = "${var.aws_region}b"
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-1b"
  }
}

# Private Subnets for RDS
resource "aws_subnet" "private_1" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = "${var.aws_region}a"

  tags = {
    Name = "${var.project_name}-private-1a"
  }
}

resource "aws_subnet" "private_2" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.12.0/24"
  availability_zone = "${var.aws_region}b"

  tags = {
    Name = "${var.project_name}-private-1b"
  }
}

# Route Table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

resource "aws_route_table_association" "public_1" {
  subnet_id      = aws_subnet.public_1.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_2" {
  subnet_id      = aws_subnet.public_2.id
  route_table_id = aws_route_table.public.id
}

# Security Groups
resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb-sg"
  description = "Security group for Application Load Balancer"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-alb-sg"
  }
}

resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-ecs-sg"
  description = "Security group for ECS tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 10001
    to_port         = 10001
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    from_port = 10001
    to_port   = 10002
    protocol  = "tcp"
    self      = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-ecs-sg"
  }
}

resource "aws_security_group" "bastion" {
  name        = "${var.project_name}-bastion-sg"
  description = "Security group for Bastion host"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["202.142.87.117/32"]
    description = "SSH access from your IP"
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["202.142.87.117/32"]
    description = "SSH access on port 443 from your IP"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-bastion-sg"
  }
}

resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-sg"
  description = "Security group for RDS database"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.bastion.id]
    description     = "PostgreSQL access from bastion host"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-rds-sg"
  }
}

# Redis Security Group
resource "aws_security_group" "redis" {
  name        = "${var.project_name}-redis-sg"
  description = "Security group for ElastiCache Redis"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
    description     = "Redis access from ECS tasks"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-redis-sg"
  }
}

# RDS Subnet Group
resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = [aws_subnet.private_1.id, aws_subnet.private_2.id]

  tags = {
    Name = "${var.project_name}-db-subnet-group"
  }
}

# RDS PostgreSQL Instance
resource "aws_db_instance" "postgres" {
  identifier     = "${var.project_name}-postgres"
  engine         = "postgres"
  engine_version = "15.15"
  instance_class = "db.t3.micro"

  allocated_storage     = 20
  max_allocated_storage = 100
  storage_encrypted     = true

  db_name  = "finance_a2a"
  username = "postgres"
  password = var.db_password

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name

  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "mon:04:00-mon:05:00"

  skip_final_snapshot = true
  publicly_accessible = false

  tags = {
    Name = "${var.project_name}-postgres"
  }
}

# ElastiCache Subnet Group
resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project_name}-redis-subnet-group"
  subnet_ids = [aws_subnet.private_1.id, aws_subnet.private_2.id]

  tags = {
    Name = "${var.project_name}-redis-subnet-group"
  }
}

# ElastiCache Redis Cluster (Serverless for cost efficiency)
resource "aws_elasticache_serverless_cache" "redis" {
  engine = "redis"
  name   = "${var.project_name}-redis"

  cache_usage_limits {
    data_storage {
      maximum = 1  # 1 GB max storage
      unit    = "GB"
    }
    ecpu_per_second {
      maximum = 1000  # 1000 ECPUs max
    }
  }

  daily_snapshot_time      = "03:00"
  description              = "Redis cache for async task tracking"
  major_engine_version     = "7"
  snapshot_retention_limit = 1
  security_group_ids       = [aws_security_group.redis.id]
  subnet_ids               = [aws_subnet.private_1.id, aws_subnet.private_2.id]

  tags = {
    Name = "${var.project_name}-redis"
  }
}

# Secrets Manager
resource "aws_secretsmanager_secret" "api_keys" {
  name        = "${var.project_name}/api-keys"
  description = "API keys for finance a2a services"
}

resource "aws_secretsmanager_secret_version" "api_keys" {
  secret_id = aws_secretsmanager_secret.api_keys.id
  secret_string = jsonencode({
    GOOGLE_API_KEY      = var.google_api_key
    PERPLEXITY_API_KEY  = var.perplexity_api_key
    FIREBASE_PROJECT_ID = var.firebase_project_id
  })
}

resource "aws_secretsmanager_secret" "database" {
  name        = "${var.project_name}/database"
  description = "Database credentials for finance a2a"
}

resource "aws_secretsmanager_secret_version" "database" {
  secret_id = aws_secretsmanager_secret.database.id
  secret_string = jsonencode({
    username = "postgres"
    password = var.db_password
    host     = aws_db_instance.postgres.endpoint
    port     = "5432"
    database = "finance_a2a"
  })
}

# Firebase Service Account (created manually in AWS Secrets Manager)
data "aws_secretsmanager_secret" "firebase_service_account" {
  name = "finance-a2a-automation/firebase-service-account"
}

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.project_name}-cluster"
  }
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "host_agent" {
  name              = "/ecs/${var.project_name}-host-agent"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-host-agent-logs"
  }
}

resource "aws_cloudwatch_log_group" "stockanalyser_agent" {
  name              = "/ecs/${var.project_name}-stockanalyser-agent"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-stockanalyser-agent-logs"
  }
}

# Stock Report Agent CloudWatch Log Group removed - now integrated into Host Agent

# Application Load Balancer
resource "aws_lb" "main" {
  name               = "${var.project_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.public_1.id, aws_subnet.public_2.id]

  enable_deletion_protection = false

  # Increase idle timeout for long-running requests (portfolio analysis with Gemini)
  idle_timeout = 300  # 5 minutes

  tags = {
    Name = "${var.project_name}-alb"
  }
}

# Target Group
resource "aws_lb_target_group" "host_agent" {
  name                 = "${var.project_name}-host-tg"
  port                 = 10001
  protocol             = "HTTP"
  vpc_id               = aws_vpc.main.id
  target_type          = "ip"
  deregistration_delay = 120  # Allow 2 minutes for in-flight requests

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 3
  }

  tags = {
    Name = "${var.project_name}-host-tg"
  }
}

# Listener
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.host_agent.arn
  }
}

# Service Discovery
resource "aws_service_discovery_private_dns_namespace" "main" {
  name = "local"
  vpc  = aws_vpc.main.id
}

resource "aws_service_discovery_service" "stockanalyser" {
  name = "stockanalyser-agent"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id

    dns_records {
      ttl  = 60
      type = "A"
    }
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

# Stock Report Service Discovery removed - now integrated into Host Agent

# S3 Bucket for Portfolio Statements
resource "aws_s3_bucket" "portfolio_statements" {
  bucket = "${var.project_name}-portfolio-statements"

  tags = {
    Name = "${var.project_name}-portfolio-statements"
  }
}

resource "aws_s3_bucket_versioning" "portfolio_statements" {
  bucket = aws_s3_bucket.portfolio_statements.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "portfolio_statements" {
  bucket = aws_s3_bucket.portfolio_statements.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# IAM Roles
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "${var.project_name}-task-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role" "ecs_task_role" {
  name = "${var.project_name}-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "s3_access" {
  name = "s3-access"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.portfolio_statements.arn,
          "${aws_s3_bucket.portfolio_statements.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "secrets_access" {
  name = "secrets-access"
  role = aws_iam_role.ecs_task_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.api_keys.arn,
          aws_secretsmanager_secret.database.arn,
          data.aws_secretsmanager_secret.firebase_service_account.arn
        ]
      }
    ]
  })
}

# Stock Report Agent ECS Task Definition removed - now integrated into Host Agent

# ECS Task Definition - Stock Analyser
resource "aws_ecs_task_definition" "stockanalyser_agent" {
  family                   = "${var.project_name}-stockanalyser-agent"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "stockanalyser-agent"
      image     = "156041436571.dkr.ecr.us-east-1.amazonaws.com/finance-a2a/stockanalyser-agent:latest"
      essential = true
      portMappings = [
        {
          containerPort = 10002
          protocol      = "tcp"
        }
      ]
      environment = [
        {
          name  = "ENVIRONMENT"
          value = "production"
        },
        {
          name  = "GOOGLE_GENAI_USE_VERTEXAI"
          value = "FALSE"
        },
        {
          name  = "MCP_DIRECTORY"
          value = "/app/finhub-mcp"
        },
        {
          name  = "DATABASE_URL"
          value = "postgresql://postgres:${var.db_password}@${aws_db_instance.postgres.endpoint}/finance_a2a?sslmode=require"
        }
      ]
      secrets = [
        {
          name      = "GOOGLE_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:GOOGLE_API_KEY::"
        },
        {
          name      = "PERPLEXITY_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:PERPLEXITY_API_KEY::"
        },
        {
          name      = "FINNHUB_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:FINNHUB_API_KEY::"
        },
        {
          name      = "ACTIVEPIECES_USERNAME"
          valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:ACTIVEPIECES_USERNAME::"
        },
        {
          name      = "ACTIVEPIECES_PASSWORD"
          valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:ACTIVEPIECES_PASSWORD::"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.stockanalyser_agent.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:10002/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name = "${var.project_name}-stockanalyser-agent"
  }
}

# ECS Task Definition - Host Agent
resource "aws_ecs_task_definition" "host_agent" {
  family                   = "${var.project_name}-host-agent"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "host-agent"
      image     = "156041436571.dkr.ecr.us-east-1.amazonaws.com/finance-a2a/host-agent:latest"
      essential = true
      portMappings = [
        {
          containerPort = 10001
          protocol      = "tcp"
        }
      ]
      environment = [
        {
          name  = "ENVIRONMENT"
          value = "production"
        },
        {
          name  = "GOOGLE_GENAI_USE_VERTEXAI"
          value = "FALSE"
        },
        {
          name  = "DATABASE_URL"
          value = "postgresql://postgres:${var.db_password}@${aws_db_instance.postgres.endpoint}/finance_a2a?sslmode=require"
        },
        {
          name  = "FREE_USER_MESSAGE_LIMIT"
          value = "30"
        },
        {
          name  = "STOCK_ANALYSER_AGENT_URL"
          value = "http://stockanalyser-agent.local:10002"
        },
        {
          name  = "S3_BUCKET_NAME"
          value = aws_s3_bucket.portfolio_statements.id
        },
        {
          name  = "AWS_DEFAULT_REGION"
          value = var.aws_region
        },
        {
          name  = "REDIS_URL"
          value = "rediss://${aws_elasticache_serverless_cache.redis.endpoint[0].address}:${aws_elasticache_serverless_cache.redis.endpoint[0].port}"
        }
      ]
      secrets = [
        {
          name      = "GOOGLE_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:GOOGLE_API_KEY::"
        },
        {
          name      = "FIREBASE_PROJECT_ID"
          valueFrom = "${aws_secretsmanager_secret.api_keys.arn}:FIREBASE_PROJECT_ID::"
        },
        {
          name      = "FIREBASE_SERVICE_ACCOUNT_JSON"
          valueFrom = data.aws_secretsmanager_secret.firebase_service_account.arn
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.host_agent.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:10001/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name = "${var.project_name}-host-agent"
  }
}

# Stock Report Agent ECS Service removed - now integrated into Host Agent

# ECS Service - Stock Analyser
resource "aws_ecs_service" "stockanalyser_agent" {
  name            = "stockanalyser-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.stockanalyser_agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.public_1.id, aws_subnet.public_2.id]
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }

  service_registries {
    registry_arn = aws_service_discovery_service.stockanalyser.arn
  }

  depends_on = [aws_lb_listener.http]

  tags = {
    Name = "${var.project_name}-stockanalyser-service"
  }
}

# ECS Service - Host Agent (with ALB)
resource "aws_ecs_service" "host_agent" {
  name            = "host-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.host_agent.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.public_1.id, aws_subnet.public_2.id]
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.host_agent.arn
    container_name   = "host-agent"
    container_port   = 10001
  }

  depends_on = [aws_lb_listener.http, aws_ecs_service.stockanalyser_agent]

  tags = {
    Name = "${var.project_name}-host-service"
  }
}

# CloudFront Response Headers Policy for CORS
resource "aws_cloudfront_response_headers_policy" "cors_policy" {
  name    = "${var.project_name}-cors-policy"
  comment = "CORS policy for API responses including error pages"

  cors_config {
    access_control_allow_credentials = true

    access_control_allow_headers {
      items = ["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"]
    }

    access_control_allow_methods {
      items = ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"]
    }

    access_control_allow_origins {
      items = [
        "https://aistockrecommender.com",
        "https://www.aistockrecommender.com",
        "https://warm-rookery-461602-i8.web.app",
        "https://warm-rookery-461602-i8.firebaseapp.com",
        "http://localhost:3000",
        "https://localhost:3000"
      ]
    }

    access_control_max_age_sec = 86400
    origin_override            = true
  }
}

# CloudFront Distribution for HTTPS
resource "aws_cloudfront_distribution" "api" {
  enabled             = true
  comment             = "${var.project_name} API Distribution"
  price_class         = "PriceClass_100"

  origin {
    domain_name = aws_lb.main.dns_name
    origin_id   = "ALB"

    custom_origin_config {
      http_port                = 80
      https_port               = 443
      origin_protocol_policy   = "http-only"
      origin_ssl_protocols     = ["TLSv1.2"]
      origin_read_timeout      = 60   # CloudFront max is 60s without Origin Shield
      origin_keepalive_timeout = 60   # Keep connections alive longer
    }
  }

  default_cache_behavior {
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]
    target_origin_id       = "ALB"
    viewer_protocol_policy = "redirect-to-https"

    # Use AWS managed policies for cache and origin request
    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id   = data.aws_cloudfront_origin_request_policy.all_viewer.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.cors_policy.id
  }

  # Custom error responses with caching disabled so errors are re-evaluated
  custom_error_response {
    error_code            = 504
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 502
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 503
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name = "${var.project_name}-api-cdn"
  }
}

# Use AWS Managed Cache Policy - CachingDisabled
# ID: 4135ea2d-6df8-44a3-9df3-4b5a84be39ad
data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

# Use AWS Managed Origin Request Policy - AllViewer
# This forwards all headers including Authorization
# ID: 216adef6-5c7f-47e4-b989-5492eafa07d3
data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewer"
}

# Bastion Host
data "aws_ami" "amazon_linux_2" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_key_pair" "bastion" {
  key_name   = "${var.project_name}-bastion-key"
  public_key = var.bastion_public_key

  tags = {
    Name = "${var.project_name}-bastion-key"
  }
}

resource "aws_iam_role" "bastion" {
  name = "${var.project_name}-bastion-role"

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
    Name = "${var.project_name}-bastion-role"
  }
}

resource "aws_iam_role_policy_attachment" "bastion_ssm" {
  role       = aws_iam_role.bastion.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "bastion" {
  name = "${var.project_name}-bastion-profile"
  role = aws_iam_role.bastion.name

  tags = {
    Name = "${var.project_name}-bastion-profile"
  }
}

resource "aws_instance" "bastion" {
  ami                         = data.aws_ami.amazon_linux_2.id
  instance_type               = "t3.micro"
  subnet_id                   = aws_subnet.public_1.id
  vpc_security_group_ids      = [aws_security_group.bastion.id]
  key_name                    = aws_key_pair.bastion.key_name
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.bastion.name

  user_data = <<-EOF
              #!/bin/bash
              yum update -y
              yum install -y postgresql
              echo "Port 443" >> /etc/ssh/sshd_config
              systemctl restart sshd
              EOF

  tags = {
    Name = "${var.project_name}-bastion"
  }
}

# Outputs
output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name (use this for HTTPS)"
  value       = aws_cloudfront_distribution.api.domain_name
}

output "cloudfront_url" {
  description = "HTTPS URL to access the application via CloudFront"
  value       = "https://${aws_cloudfront_distribution.api.domain_name}"
}

output "rds_endpoint" {
  description = "Endpoint of the RDS database"
  value       = aws_db_instance.postgres.endpoint
}

output "redis_endpoint" {
  description = "Endpoint of the ElastiCache Redis cluster"
  value       = "${aws_elasticache_serverless_cache.redis.endpoint[0].address}:${aws_elasticache_serverless_cache.redis.endpoint[0].port}"
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "application_url" {
  description = "URL to access the application"
  value       = "http://${aws_lb.main.dns_name}"
}

output "bastion_public_ip" {
  description = "Public IP address of the bastion host"
  value       = aws_instance.bastion.public_ip
}

output "bastion_ssh_command" {
  description = "SSH command to connect to bastion host"
  value       = "ssh -i ~/.ssh/finance-a2a-bastion -p 443 ec2-user@${aws_instance.bastion.public_ip}"
}

output "database_tunnel_command" {
  description = "SSH tunnel command for database access"
  value       = "ssh -i ~/.ssh/finance-a2a-bastion -p 443 -L 5432:${aws_db_instance.postgres.address}:5432 ec2-user@${aws_instance.bastion.public_ip} -N"
}
