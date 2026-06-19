# ===========================================================================
# RDS PostgreSQL (pgvector-capable).
#
# COST NOTES:
#   - db.t4g.micro: cheapest ARM burstable, ~$12-13/month on-demand in
#     ap-south-1. Burst performance is plenty for a demo's query volume.
#   - gp3 20 GB: gp3 is cheaper than gp2 at this size and the 20 GB floor keeps
#     storage cost minimal (~$2-3/month).
#   - multi_az = false: single-AZ roughly HALVES the instance cost. Acceptable
#     for a demo; NOT acceptable for production with paying customers (an AZ
#     failure means downtime and potential data loss between backups).
#   - backup_retention_period = 1: minimum that still keeps automated backups
#     (and thus point-in-time recovery for ~1 day). Production should use 7+.
#   - deletion_protection = false + skip_final_snapshot = true: so the teardown
#     script can actually destroy the DB. Production MUST set deletion_protection
#     = true and skip_final_snapshot = false.
#
# pgvector: RDS Postgres 16 ships `vector` as a supported extension. No
# parameter-group change or shared_preload_libraries entry is required — the
# app's init_db() runs `CREATE EXTENSION IF NOT EXISTS vector` on startup, which
# RDS permits for the master user. Hence no custom parameter group here.
# ===========================================================================

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db-subnets"
  subnet_ids = aws_subnet.private[*].id
  tags       = { Name = "${local.name_prefix}-db-subnets" }
}

resource "aws_db_instance" "main" {
  identifier     = "${local.name_prefix}-postgres"
  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  allocated_storage = var.db_allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true # free with the default AWS-managed key; good practice

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period    = 1
  auto_minor_version_upgrade = true
  apply_immediately          = true # demo: take changes now rather than in a window

  # Demo teardown convenience — see cost note above; flip both for production.
  deletion_protection = false
  skip_final_snapshot = true

  # Performance Insights and Enhanced Monitoring are intentionally OFF: both add
  # cost and are unnecessary at demo scale.
  performance_insights_enabled = false
  monitoring_interval          = 0

  tags = { Name = "${local.name_prefix}-postgres" }
}
