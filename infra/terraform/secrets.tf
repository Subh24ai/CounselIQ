# ===========================================================================
# Application secrets — SSM Parameter Store (SecureString).
#
# COST NOTE — SSM vs Secrets Manager:
#   AWS Secrets Manager charges ~$0.40 per secret per month plus per-API-call
#   fees. Its headline feature is built-in rotation, which this demo does not
#   need. SSM Parameter Store SecureString (Standard tier) is GENUINELY FREE for
#   storage and API calls and is encrypted at rest with the AWS-managed
#   `aws/ssm` KMS key (also free). So we use SSM here. If you later need
#   automatic credential rotation, switch DATABASE_URL/keys to Secrets Manager.
#
# Values come from terraform.tfvars (secrets) and from RDS/Redis outputs
# (connection strings) — NEVER hardcoded. ECS injects these into containers via
# the task definition `secrets` block (see ecs.tf), referencing the parameter
# ARNs below.
#
# All parameters live under /counseliq/* so the task execution role's SSM read
# permission can be scoped to exactly that path (see iam.tf).
# ===========================================================================

locals {
  ssm_prefix = "/${var.project_name}"

  # Connection strings assembled from live RDS/Redis attributes.
  # asyncpg driver to match the app's SQLAlchemy async engine.
  database_url = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${aws_db_instance.main.address}:5432/${var.db_name}"

  redis_host            = aws_elasticache_cluster.main.cache_nodes[0].address
  redis_url             = "redis://${local.redis_host}:6379/0"
  celery_broker_url     = "redis://${local.redis_host}:6379/1"
  celery_result_backend = "redis://${local.redis_host}:6379/2"

  # name -> value. Optional LLM keys are dropped when empty (SSM rejects empty
  # values, and the app only requires one provider key).
  secret_values = merge(
    {
      JWT_SECRET_KEY        = var.jwt_secret_key
      DATABASE_URL          = local.database_url
      REDIS_URL             = local.redis_url
      CELERY_BROKER_URL     = local.celery_broker_url
      CELERY_RESULT_BACKEND = local.celery_result_backend
    },
    var.anthropic_api_key != "" ? { ANTHROPIC_API_KEY = var.anthropic_api_key } : {},
    var.groq_api_key != "" ? { GROQ_API_KEY = var.groq_api_key } : {},
  )
}

resource "aws_ssm_parameter" "app" {
  for_each = local.secret_values

  name        = "${local.ssm_prefix}/${each.key}"
  description = "CounselIQ ${each.key}"
  type        = "SecureString" # encrypted with the free AWS-managed aws/ssm key
  value       = each.value
  tier        = "Standard" # free; values up to 4 KB

  tags = { Name = "${local.ssm_prefix}/${each.key}" }
}
