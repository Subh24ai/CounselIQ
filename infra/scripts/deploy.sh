#!/bin/bash
# ===========================================================================
# CounselIQ end-to-end deploy script.
#
# Provisions/updates infrastructure with Terraform, builds and pushes the
# backend + frontend container images to ECR, runs database migrations as a
# one-off ECS task, rolls out the ECS services, and verifies the deployment
# against the live /health/detailed endpoint.
#
# Idempotent: safe to re-run. On the first run it creates the ECR repositories
# before the rest of the stack so the ECS services have an image to pull.
#
# Usage:   ./deploy.sh
# Requires: terraform >= 1.5, awscli v2 (configured), docker with buildx.
# Env overrides:
#   IMAGE_TAG        image tag to build/push/deploy (default: git short SHA, else "latest")
#   DOCKER_PLATFORM  build platform (default: linux/arm64 — must match
#                    var.fargate_cpu_architecture, ARM64 by default)
# ===========================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TF_DIR="${SCRIPT_DIR}/../terraform"
BACKEND_CTX="${SCRIPT_DIR}/../../backend"
FRONTEND_CTX="${SCRIPT_DIR}/../../frontend"

DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/arm64}"
IMAGE_TAG="${IMAGE_TAG:-$(git -C "${SCRIPT_DIR}" rev-parse --short HEAD 2>/dev/null || echo latest)}"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

tf() { terraform -chdir="${TF_DIR}" "$@"; }
tfout() { tf output -raw "$1"; }

command -v terraform >/dev/null || die "terraform not found on PATH"
command -v aws >/dev/null       || die "aws CLI not found on PATH"
command -v docker >/dev/null    || die "docker not found on PATH"

# ---------------------------------------------------------------------------
# 1. Init + create the ECR repos first (so images exist before services start).
# ---------------------------------------------------------------------------
log "terraform init"
tf init -input=false

log "terraform apply (ECR repositories only — first so we have somewhere to push)"
tf apply -input=false -auto-approve -target=aws_ecr_repository.this

AWS_REGION="$(tfout aws_region)"
ECR_BACKEND="$(tfout ecr_backend_repository_url)"
ECR_FRONTEND="$(tfout ecr_frontend_repository_url)"
REGISTRY="${ECR_BACKEND%/*}" # account.dkr.ecr.<region>.amazonaws.com

# ---------------------------------------------------------------------------
# 2. Build + push the backend image (ARM64 to match the Fargate platform).
# ---------------------------------------------------------------------------
log "ECR login (${REGISTRY})"
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${REGISTRY}"

# Ensure a buildx builder capable of the target platform exists.
docker buildx inspect counseliq >/dev/null 2>&1 \
  || docker buildx create --name counseliq --use >/dev/null
docker buildx use counseliq

log "build + push backend image (${IMAGE_TAG})"
docker buildx build --platform "${DOCKER_PLATFORM}" \
  -t "${ECR_BACKEND}:${IMAGE_TAG}" -t "${ECR_BACKEND}:latest" \
  --push "${BACKEND_CTX}"

# ---------------------------------------------------------------------------
# 3. Full infrastructure apply. After this RDS/Redis/ALB/ECS all exist, and the
#    app_url / task-def / network outputs the rest of the script needs are set.
#    Done before the frontend build because the frontend bundle must be built
#    with NEXT_PUBLIC_API_URL = the real app URL, which comes from this apply.
# ---------------------------------------------------------------------------
log "terraform apply (full stack)"
tf apply -input=false -auto-approve -var "container_image_tag=${IMAGE_TAG}"

APP_URL="$(tfout app_url)"
ALB_DNS="$(tfout alb_dns_name)"
CLUSTER="$(tfout ecs_cluster_name)"
PREFIX="$(tfout service_name_prefix)"
BACKEND_TASKDEF="$(tfout backend_task_definition)"
ECS_SG="$(tfout ecs_security_group_id)"
# Comma-separated subnet list for the run-task network config.
SUBNETS="$(tf output -json private_subnet_ids | tr -d '[]" \n')"

log "build + push frontend image (${IMAGE_TAG}) with NEXT_PUBLIC_API_URL=${APP_URL}"
docker buildx build --platform "${DOCKER_PLATFORM}" \
  --build-arg "NEXT_PUBLIC_API_URL=${APP_URL}" \
  -t "${ECR_FRONTEND}:${IMAGE_TAG}" -t "${ECR_FRONTEND}:latest" \
  --push "${FRONTEND_CTX}"

# ---------------------------------------------------------------------------
# 4. Run database migrations as a one-off ECS task (alembic upgrade head).
#    Reuses the backend task definition (which already has DATABASE_URL injected
#    from SSM) with a command override, in the private subnets via the ECS SG.
# ---------------------------------------------------------------------------
log "run database migrations (alembic upgrade head)"
NET_CONFIG="awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${ECS_SG}],assignPublicIp=DISABLED}"
OVERRIDES='{"containerOverrides":[{"name":"backend","command":["alembic","upgrade","head"]}]}'

TASK_ARN="$(aws ecs run-task \
  --cluster "${CLUSTER}" \
  --launch-type FARGATE \
  --task-definition "${BACKEND_TASKDEF}" \
  --network-configuration "${NET_CONFIG}" \
  --overrides "${OVERRIDES}" \
  --region "${AWS_REGION}" \
  --query 'tasks[0].taskArn' --output text)"
[ -n "${TASK_ARN}" ] && [ "${TASK_ARN}" != "None" ] || die "failed to start migration task"

echo "    migration task: ${TASK_ARN}"
aws ecs wait tasks-stopped --cluster "${CLUSTER}" --tasks "${TASK_ARN}" --region "${AWS_REGION}"

EXIT_CODE="$(aws ecs describe-tasks --cluster "${CLUSTER}" --tasks "${TASK_ARN}" \
  --region "${AWS_REGION}" \
  --query 'tasks[0].containers[?name==`backend`].exitCode | [0]' --output text)"
[ "${EXIT_CODE}" = "0" ] || die "migration task exited with code ${EXIT_CODE} (check the backend CloudWatch logs)"
echo "    migrations applied."

# ---------------------------------------------------------------------------
# 5. Roll out the services so they pick up the freshly pushed images.
# ---------------------------------------------------------------------------
log "force new deployment of backend, worker, frontend"
for svc in backend worker frontend; do
  aws ecs update-service --cluster "${CLUSTER}" --service "${PREFIX}-${svc}" \
    --force-new-deployment --region "${AWS_REGION}" >/dev/null
  echo "    rollout triggered: ${PREFIX}-${svc}"
done

log "waiting for backend + frontend services to reach steady state"
aws ecs wait services-stable --cluster "${CLUSTER}" \
  --services "${PREFIX}-backend" "${PREFIX}-frontend" --region "${AWS_REGION}"

# ---------------------------------------------------------------------------
# 6. Health check against the live HTTPS endpoint. DNS + cert propagation can
#    lag on a first deploy, so we retry for a few minutes.
# ---------------------------------------------------------------------------
log "health check: ${APP_URL}/health/detailed"
HEALTH_OK=""
for attempt in $(seq 1 30); do
  BODY="$(curl -fsS --max-time 10 "${APP_URL}/health/detailed" 2>/dev/null || true)"
  if printf '%s' "${BODY}" | grep -q '"status":"ok"'; then
    HEALTH_OK="yes"
    echo "    healthy: ${BODY}"
    break
  fi
  echo "    attempt ${attempt}/30: not healthy yet (DNS/cert/rollout may still be settling)…"
  sleep 10
done
[ -n "${HEALTH_OK}" ] || die "health check did not pass for ${APP_URL}/health/detailed"

# ---------------------------------------------------------------------------
# 7. Done.
# ---------------------------------------------------------------------------
printf '\n\033[1;32m✓ Deployment complete.\033[0m\n'
echo "  App URL (HTTPS):  ${APP_URL}"
echo "  ALB DNS name:     ${ALB_DNS}"
echo "  Image tag:        ${IMAGE_TAG}"
echo "  Region:           ${AWS_REGION}"
