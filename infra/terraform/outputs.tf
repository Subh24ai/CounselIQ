# ===========================================================================
# Outputs — the handful of values needed to deploy and reach the app.
# ===========================================================================

output "alb_dns_name" {
  description = "Raw public DNS name of the load balancer (the custom domain aliases to this)."
  value       = aws_lb.main.dns_name
}

output "app_url" {
  description = "Open this in a browser to reach the app over HTTPS on the custom domain."
  value       = "https://${var.domain_name}"
}

output "acm_certificate_arn" {
  description = "ARN of the issued ACM certificate bound to the HTTPS listener."
  value       = aws_acm_certificate_validation.main.certificate_arn
}

output "ecr_backend_repository_url" {
  description = "Push the backend image here (tag with var.container_image_tag)."
  value       = aws_ecr_repository.this["backend"].repository_url
}

output "ecr_frontend_repository_url" {
  description = "Push the frontend image here."
  value       = aws_ecr_repository.this["frontend"].repository_url
}

output "rds_endpoint" {
  description = "RDS Postgres endpoint (host:port). Reachable only from within the VPC."
  value       = aws_db_instance.main.endpoint
}

output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint host."
  value       = aws_elasticache_cluster.main.cache_nodes[0].address
}

output "s3_bucket_name" {
  description = "Documents bucket name (injected into tasks as S3_BUCKET_NAME)."
  value       = aws_s3_bucket.documents.id
}

output "ecs_cluster_name" {
  description = "ECS cluster name (used by the deploy script for force-new-deployment)."
  value       = aws_ecs_cluster.main.name
}

# --- Values the deploy script needs to launch the one-off migration task ----
output "private_subnet_ids" {
  description = "Private subnet IDs for running the one-off Alembic migration task."
  value       = aws_subnet.private[*].id
}

output "ecs_security_group_id" {
  description = "Security group attached to ECS tasks (used by the migration run-task)."
  value       = aws_security_group.ecs.id
}

output "backend_task_definition" {
  description = "Backend task definition family — invoked with an Alembic command override to migrate."
  value       = aws_ecs_task_definition.backend.family
}

output "service_name_prefix" {
  description = "Prefix of the ECS service names; the deploy script appends -backend/-worker/-frontend."
  value       = local.name_prefix
}

output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.main.id
}

output "aws_region" {
  description = "Region everything is deployed in."
  value       = var.aws_region
}
