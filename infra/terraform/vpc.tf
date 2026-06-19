# ===========================================================================
# VPC and networking.
#
# Layout (2 AZs):
#   - 2 public subnets  -> ALB + the single NAT Gateway
#   - 2 private subnets -> ECS tasks, RDS, ElastiCache (no public IPs)
#
# COST NOTE — SINGLE NAT GATEWAY:
#   A NAT Gateway costs ~$0.045/hr (~$32/month) PLUS data processing in
#   ap-south-1, and the textbook HA pattern is one NAT per AZ. For a demo we
#   deliberately run ONE shared NAT Gateway for both private subnets. The
#   tradeoff: if the NAT's AZ goes down, private-subnet egress (ECR pulls,
#   outbound LLM API calls) is interrupted until it recovers. That reduced AZ
#   redundancy is acceptable for a portfolio project and roughly halves NAT
#   cost. For real production, run one NAT per AZ.
# ===========================================================================

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${local.name_prefix}-vpc" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${local.name_prefix}-igw" }
}

# --- Public subnets (ALB + NAT) --------------------------------------------
resource "aws_subnet" "public" {
  count                   = var.az_count
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${local.name_prefix}-public-${local.azs[count.index]}"
    Tier = "public"
  }
}

# --- Private subnets (ECS tasks, RDS, Redis) -------------------------------
resource "aws_subnet" "private" {
  count             = var.az_count
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  availability_zone = local.azs[count.index]

  tags = {
    Name = "${local.name_prefix}-private-${local.azs[count.index]}"
    Tier = "private"
  }
}

# --- Single NAT Gateway -----------------------------------------------------
# Placed in the first public subnet; both private subnets route egress here.
resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "${local.name_prefix}-nat-eip" }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  tags          = { Name = "${local.name_prefix}-nat" }

  depends_on = [aws_internet_gateway.main]
}

# --- Route tables -----------------------------------------------------------
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${local.name_prefix}-rt-public" }
}

resource "aws_route_table_association" "public" {
  count          = var.az_count
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# One shared private route table -> the single NAT Gateway.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = { Name = "${local.name_prefix}-rt-private" }
}

resource "aws_route_table_association" "private" {
  count          = var.az_count
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# --- S3 Gateway VPC Endpoint (FREE) -----------------------------------------
# Gateway endpoints have NO hourly charge and NO data processing charge. Routing
# S3 traffic (document upload/download, Textract reading objects) through this
# endpoint keeps it off the NAT Gateway, avoiding NAT data-processing fees for
# the largest traffic source in the app. Pure cost win, no downside.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = { Name = "${local.name_prefix}-s3-endpoint" }
}

# ===========================================================================
# Security groups (least privilege; each tier only accepts traffic from the
# tier in front of it).
# ===========================================================================

# ALB: public ingress on 80/443.
resource "aws_security_group" "alb" {
  name_prefix = "${local.name_prefix}-alb-"
  description = "ALB - public HTTP/HTTPS ingress"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from anywhere (listener added when an ACM cert/domain exists)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle { create_before_destroy = true }
  tags = { Name = "${local.name_prefix}-alb-sg" }
}

# ECS tasks: only accept traffic from the ALB, on the app ports.
resource "aws_security_group" "ecs" {
  name_prefix = "${local.name_prefix}-ecs-"
  description = "ECS tasks - ingress from ALB only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Backend port from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description     = "Frontend port from ALB"
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "All outbound (ECR pulls, SSM, LLM APIs, RDS, Redis)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle { create_before_destroy = true }
  tags = { Name = "${local.name_prefix}-ecs-sg" }
}

# RDS: only Postgres, only from ECS tasks.
resource "aws_security_group" "rds" {
  name_prefix = "${local.name_prefix}-rds-"
  description = "RDS - Postgres from ECS only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Postgres from ECS tasks"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle { create_before_destroy = true }
  tags = { Name = "${local.name_prefix}-rds-sg" }
}

# Redis: only 6379, only from ECS tasks.
resource "aws_security_group" "redis" {
  name_prefix = "${local.name_prefix}-redis-"
  description = "ElastiCache - Redis from ECS only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Redis from ECS tasks"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle { create_before_destroy = true }
  tags = { Name = "${local.name_prefix}-redis-sg" }
}
