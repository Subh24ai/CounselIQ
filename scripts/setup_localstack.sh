#!/bin/bash
# Creates the S3 bucket in LocalStack for local development.
#
# Usage (after `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d localstack`):
#   ./scripts/setup_localstack.sh
set -euo pipefail

ENDPOINT="http://localhost:4566"
REGION="ap-south-1"
BUCKET="counseliq-dev"

aws --endpoint-url="${ENDPOINT}" s3 mb "s3://${BUCKET}" --region "${REGION}"
echo "LocalStack S3 bucket created: ${BUCKET}"
