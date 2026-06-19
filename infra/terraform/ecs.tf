# ===========================================================================
# ECS on Fargate — cluster, log groups, task definitions, and services.
#
# Three services from two images:
#   - backend  (FastAPI, :8000)  -> behind ALB,   on-demand FARGATE
#   - frontend (Next.js, :3000)  -> behind ALB,   on-demand FARGATE
#   - worker   (Celery)          -> no LB,        FARGATE_SPOT (see cost note)
#
# COST NOTES:
#   - Fargate is billed per vCPU-second + GB-second. Total steady-state size is
#     1.25 vCPU / 3.5 GB across all three tasks (see variables.tf). At one task
#     each this is the dominant compute cost — ~$45-60/month. See COST_ESTIMATE.
#   - ARM64 (Graviton) Fargate is ~20% cheaper than x86 AND matches images built
#     on Apple Silicon without emulation. Default below is ARM64; the deploy
#     script must build/push matching-arch images (docker buildx --platform).
#   - The WORKER runs on FARGATE_SPOT: up to ~70% cheaper, with the tradeoff of
#     possible interruption. That's acceptable because Celery work is async and
#     idempotent and the app already has stale-job recovery. The user-facing
#     backend/frontend stay on on-demand FARGATE so they aren't reclaimed.
#   - Container Insights is OFF (it ships extra CloudWatch metrics that cost
#     money); basic ECS metrics remain free.
#   - Log retention is short (var.log_retention_days, default 7) to keep
#     CloudWatch Logs storage negligible.
# ===========================================================================

variable "fargate_cpu_architecture" {
  description = <<-EOT
    CPU architecture for Fargate tasks. ARM64 (Graviton) is ~20% cheaper and
    matches images built on Apple Silicon. Must match the architecture of the
    images pushed to ECR (build with `docker buildx --platform linux/arm64`).
    Set to X86_64 if you build amd64 images.
  EOT
  type        = string
  default     = "ARM64"
}

resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "disabled" # avoids extra CloudWatch metric cost
  }

  tags = { Name = "${local.name_prefix}-cluster" }
}

# Register both capacity providers so services can choose on-demand vs spot.
resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
}

# --- CloudWatch log groups (one per service) -------------------------------
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${local.name_prefix}/backend"
  retention_in_days = var.log_retention_days
  tags              = { Name = "${local.name_prefix}-backend-logs" }
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${local.name_prefix}/worker"
  retention_in_days = var.log_retention_days
  tags              = { Name = "${local.name_prefix}-worker-logs" }
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/ecs/${local.name_prefix}/frontend"
  retention_in_days = var.log_retention_days
  tags              = { Name = "${local.name_prefix}-frontend-logs" }
}

# ---------------------------------------------------------------------------
# Shared container config
# ---------------------------------------------------------------------------
locals {
  backend_image  = "${aws_ecr_repository.this["backend"].repository_url}:${var.container_image_tag}"
  frontend_image = "${aws_ecr_repository.this["frontend"].repository_url}:${var.container_image_tag}"

  # Public entry point: the custom domain over HTTPS (see route53.tf / alb.tf).
  # This is what the browser talks to, so it drives both CORS and the frontend's
  # API base URL.
  app_base_url = "https://${var.domain_name}"

  # Non-secret env shared by backend + worker. ENVIRONMENT=production engages the
  # app's production safety checks (e.g. it refuses to boot with a weak
  # JWT_SECRET_KEY — so the value in tfvars must be >=32 random chars).
  app_environment = [
    { name = "ENVIRONMENT", value = "production" },
    { name = "LOG_LEVEL", value = "INFO" },
    { name = "AWS_REGION", value = var.aws_region },
    { name = "S3_BUCKET_NAME", value = aws_s3_bucket.documents.id },
    { name = "LLM_PROVIDER", value = "auto" },
    # Browser origin for CORS is the public HTTPS domain the frontend is served on.
    { name = "CORS_ORIGINS", value = local.app_base_url },
  ]

  # All SSM parameters are injected as secret env vars into backend + worker.
  app_secrets = [
    for k, p in aws_ssm_parameter.app : { name = k, valueFrom = p.arn }
  ]
}

# ---------------------------------------------------------------------------
# Backend task definition (FastAPI; uses the image's default uvicorn CMD)
# ---------------------------------------------------------------------------
resource "aws_ecs_task_definition" "backend" {
  family                   = "${local.name_prefix}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.backend_cpu
  memory                   = var.backend_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  runtime_platform {
    cpu_architecture        = var.fargate_cpu_architecture
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name        = "backend"
      image       = local.backend_image
      essential   = true
      environment = local.app_environment
      secrets     = local.app_secrets
      portMappings = [
        { containerPort = 8000, protocol = "tcp" }
      ]
      healthCheck = {
        command     = ["CMD-SHELL", "curl -fsS http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "backend"
        }
      }
    }
  ])

  tags = { Name = "${local.name_prefix}-backend" }
}

# ---------------------------------------------------------------------------
# Worker task definition (Celery worker; command overrides the image CMD)
# ---------------------------------------------------------------------------
resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name_prefix}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  runtime_platform {
    cpu_architecture        = var.fargate_cpu_architecture
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name        = "worker"
      image       = local.backend_image # same image as backend, different command
      essential   = true
      command     = ["celery", "-A", "app.tasks.celery_app:celery_app", "worker", "--loglevel=info", "--concurrency=2"]
      environment = local.app_environment
      secrets     = local.app_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])

  tags = { Name = "${local.name_prefix}-worker" }
}

# ---------------------------------------------------------------------------
# Frontend task definition (Next.js standalone server)
# ---------------------------------------------------------------------------
resource "aws_ecs_task_definition" "frontend" {
  family                   = "${local.name_prefix}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.frontend_cpu
  memory                   = var.frontend_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  runtime_platform {
    cpu_architecture        = var.fargate_cpu_architecture
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = "frontend"
      image     = local.frontend_image
      essential = true
      environment = [
        { name = "NODE_ENV", value = "production" },
        { name = "PORT", value = "3000" },
        # NOTE: NEXT_PUBLIC_* values are inlined at BUILD time. This runtime value
        # is a backstop; the deploy script must pass NEXT_PUBLIC_API_URL as a
        # build-arg so the browser bundle points at the public HTTPS domain.
        { name = "NEXT_PUBLIC_API_URL", value = local.app_base_url },
      ]
      portMappings = [
        { containerPort = 3000, protocol = "tcp" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.frontend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "frontend"
        }
      }
    }
  ])

  tags = { Name = "${local.name_prefix}-frontend" }
}

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
resource "aws_ecs_service" "backend" {
  name            = "${local.name_prefix}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 1

  capacity_provider_strategy {
    capacity_provider = "FARGATE" # user-facing: on-demand, never spot-reclaimed
    weight            = 1
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false # private subnet; egress via NAT
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  health_check_grace_period_seconds  = 90
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  # The HTTPS listener is the one that forwards to targets (HTTP:80 only
  # redirects), so the service waits on it before registering.
  depends_on = [aws_lb_listener.https]
  tags       = { Name = "${local.name_prefix}-backend-svc" }
}

resource "aws_ecs_service" "frontend" {
  name            = "${local.name_prefix}-frontend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = 1

  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 3000
  }

  health_check_grace_period_seconds  = 60
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  depends_on = [aws_lb_listener.https]
  tags       = { Name = "${local.name_prefix}-frontend-svc" }
}

resource "aws_ecs_service" "worker" {
  name            = "${local.name_prefix}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 1

  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT" # async, interruption-tolerant -> cheapest
    weight            = 1
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  # No load balancer. Allow the single task to be replaced in place on deploy
  # (a brief processing gap is fine for background work).
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  tags = { Name = "${local.name_prefix}-worker-svc" }
}
