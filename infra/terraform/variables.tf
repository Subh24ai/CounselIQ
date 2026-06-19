# ===========================================================================
# Input variables. Defaults are the cheapest viable settings for a demo.
# Anything sensitive (DB password, API keys, JWT secret) has NO default and
# must be supplied via terraform.tfvars (gitignored) — never hardcoded here.
# ===========================================================================

variable "aws_region" {
  description = "AWS region. Matches the app's AWS_REGION config."
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  description = "Short project slug used to name and tag resources."
  type        = string
  default     = "counseliq"
}

variable "environment" {
  description = "Environment name used in resource names/tags (e.g. production, staging)."
  type        = string
  default     = "production"
}

# --- DNS / TLS --------------------------------------------------------------

variable "domain_name" {
  description = <<-EOT
    Fully-qualified domain the app is served on, e.g. "app.counseliq.in". The
    ACM certificate is issued for this name and the Route53 A-record points it at
    the ALB. REQUIRED — no default, because every deployment uses its own domain.
  EOT
  type        = string
}

variable "hosted_zone_name" {
  description = <<-EOT
    The Route53 public hosted zone that is authoritative for domain_name, e.g.
    "counseliq.in" (no trailing dot). Must already exist and have its nameservers
    registered with your domain registrar. REQUIRED — no default.
  EOT
  type        = string
}

# --- Networking -------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = <<-EOT
    Number of Availability Zones to spread subnets across. 2 gives the ALB and
    RDS basic multi-AZ subnet placement without the cost of multi-AZ failover.
    Note: we still run only ONE NAT Gateway (see vpc.tf) to keep cost down.
  EOT
  type        = number
  default     = 2
}

# --- RDS Postgres -----------------------------------------------------------

variable "db_instance_class" {
  description = "RDS instance class. db.t4g.micro is the cheapest ARM burstable."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_engine_version" {
  description = <<-EOT
    Postgres major version. 16 supports the pgvector extension the app relies
    on. Specifying the major only lets RDS pick a supported minor automatically.
  EOT
  type        = string
  default     = "16"
}

variable "db_allocated_storage" {
  description = "RDS storage in GB. 20 is the sensible minimum on gp3."
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Initial Postgres database name."
  type        = string
  default     = "counseliq"
}

variable "db_username" {
  description = "Master DB username."
  type        = string
  default     = "counseliq"
}

variable "db_password" {
  description = "Master DB password. REQUIRED — set in terraform.tfvars."
  type        = string
  sensitive   = true
}

# --- ElastiCache Redis ------------------------------------------------------

variable "redis_node_type" {
  description = "ElastiCache node type. cache.t4g.micro is the cheapest ARM node."
  type        = string
  default     = "cache.t4g.micro"
}

variable "redis_engine_version" {
  description = "Redis engine version (7.x supports the async redis-py features in use)."
  type        = string
  default     = "7.1"
}

# --- ECS / Fargate task sizing ----------------------------------------------
# Fargate is billed per vCPU-second and GB-second, so these directly drive
# cost (see COST_ESTIMATE.md). Values are the smallest that comfortably run
# each workload:
#   - backend: FastAPI + boto3 + lazy-loaded torch embedding model on some
#     request paths (regulatory impact matching) -> needs ~1 GB.
#   - worker:  full 5-agent analysis + sentence-transformers (torch) -> ~2 GB.
#   - frontend: Next.js standalone server -> light, 0.25 vCPU / 0.5 GB.

variable "backend_cpu" {
  description = "Fargate CPU units for the backend task (256 = 0.25 vCPU)."
  type        = number
  default     = 512
}

variable "backend_memory" {
  description = "Fargate memory (MiB) for the backend task."
  type        = number
  default     = 1024
}

variable "worker_cpu" {
  description = "Fargate CPU units for the Celery worker task."
  type        = number
  default     = 512
}

variable "worker_memory" {
  description = "Fargate memory (MiB) for the Celery worker task (torch needs headroom)."
  type        = number
  default     = 2048
}

variable "frontend_cpu" {
  description = "Fargate CPU units for the frontend task."
  type        = number
  default     = 256
}

variable "frontend_memory" {
  description = "Fargate memory (MiB) for the frontend task."
  type        = number
  default     = 512
}

variable "container_image_tag" {
  description = <<-EOT
    Image tag deployed to ECS for both backend and frontend. The deploy script
    builds and pushes this tag to ECR, then forces a new ECS deployment.
  EOT
  type        = string
  default     = "latest"
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention. 7 days keeps log storage cost trivial."
  type        = number
  default     = 7
}

# --- Application secrets (stored in SSM Parameter Store, SecureString) -------
# At least one of anthropic/groq must be non-empty (the app refuses to boot
# otherwise). Empty values are simply not created as parameters.

variable "jwt_secret_key" {
  description = "JWT signing secret (>=32 random chars). REQUIRED — set in tfvars."
  type        = string
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "Anthropic API key (primary LLM). Optional if groq_api_key is set."
  type        = string
  sensitive   = true
  default     = ""
}

variable "groq_api_key" {
  description = "Groq API key (fallback LLM). Optional if anthropic_api_key is set."
  type        = string
  sensitive   = true
  default     = ""
}
