# ===========================================================================
# ElastiCache Redis (Celery broker/result backend + app cache/pubsub).
#
# COST NOTES:
#   - cache.t4g.micro: cheapest ARM node, ~$11-12/month in ap-south-1.
#   - SINGLE NODE, no replica / no automatic failover: a replica would roughly
#     double cost. A single node is acceptable for a demo — if the node fails,
#     in-flight Celery tasks are lost and recovered by the app's stale-job
#     recovery, and the cache simply repopulates. NOT acceptable for production,
#     where you'd use a replication group with Multi-AZ failover.
#
# A standalone (cluster-mode-disabled) `aws_elasticache_cluster` is the cheapest
# possible Redis on ElastiCache. It exposes the usual 16 logical DBs, so the
# app's split across db 0 (cache/pubsub), db 1 (Celery broker) and db 2 (Celery
# results) works without any extra configuration.
# ===========================================================================

resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name_prefix}-redis-subnets"
  subnet_ids = aws_subnet.private[*].id
  tags       = { Name = "${local.name_prefix}-redis-subnets" }
}

resource "aws_elasticache_cluster" "main" {
  cluster_id           = "${local.name_prefix}-redis"
  engine               = "redis"
  engine_version       = var.redis_engine_version
  node_type            = var.redis_node_type
  num_cache_nodes      = 1
  port                 = 6379
  parameter_group_name = "default.redis7"

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  # Snapshots add S3 storage cost and aren't meaningful for an ephemeral
  # broker/cache; disabled for the demo.
  snapshot_retention_limit = 0

  tags = { Name = "${local.name_prefix}-redis" }
}
