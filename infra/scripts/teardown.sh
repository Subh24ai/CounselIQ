#!/bin/bash
# ===========================================================================
# Destroy ALL CounselIQ AWS infrastructure. After this completes, the project
# incurs no further AWS charges.
#
# Note: the S3 documents bucket and RDS instance are configured for demo
# teardown (force_destroy / skip_final_snapshot), so their DATA IS DELETED.
# ===========================================================================
set -euo pipefail

echo "This will DESTROY all CounselIQ AWS infrastructure (including the S3"
echo "documents bucket and the RDS database — data will be lost). Continue? (y/N)"
read -r confirm
if [ "$confirm" != "y" ]; then
  echo "Aborted."
  exit 0
fi

cd "$(dirname "$0")/../terraform"
terraform destroy -auto-approve

echo "Infrastructure destroyed. No further AWS charges from this project."
