# CounselIQ — Infrastructure (AWS, Terraform)

End-to-end AWS deployment for CounselIQ: an ECS Fargate stack behind an
HTTPS-terminating Application Load Balancer, with RDS PostgreSQL (pgvector),
ElastiCache Redis, ECR, S3, and SSM-stored secrets — all in **ap-south-1**.

```
infra/
├── terraform/   the full stack (one .tf file per concern)
├── scripts/     deploy.sh (build → migrate → roll out → verify) and teardown.sh
├── README.md    this file
└── COST_ESTIMATE.md   monthly cost breakdown
```

## What gets created

| Concern | Resource |
| ------- | -------- |
| Network | VPC, 2 public + 2 private subnets, single NAT GW, S3 gateway endpoint |
| Ingress | ALB with **HTTPS:443** (TLS 1.3) and **HTTP:80 → 301 redirect to HTTPS** |
| TLS/DNS | ACM certificate (DNS-validated, in ap-south-1) + Route53 A-record → ALB |
| Compute | ECS Fargate: `backend` + `frontend` (on-demand) and `worker` (FARGATE_SPOT) |
| Data    | RDS PostgreSQL 16 (private), ElastiCache Redis 7 (private) |
| Images  | ECR repos for backend + frontend (scan-on-push, 5-image lifecycle) |
| Storage | Private S3 documents bucket (SSE, public access blocked) |
| Secrets | SSM Parameter Store SecureStrings under `/counseliq/*` |

## Prerequisites

- **Terraform >= 1.6**
- **AWS CLI v2**, configured for an account/role with permissions to create the
  above, default region **ap-south-1** (`aws configure`)
- **Docker** with **buildx** (images are built for `linux/arm64` to match the
  Fargate Graviton runtime)
- A **domain with a Route53 public hosted zone** that already exists and whose
  nameservers are registered with your registrar. Terraform issues the ACM
  certificate and creates the app's DNS record inside this zone, but it does not
  create the zone or register nameservers.

## First-time setup

```bash
cd infra/terraform

cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars and set, at minimum:
#   domain_name       e.g. "app.counseliq.in"
#   hosted_zone_name  e.g. "counseliq.in"
#   db_password       a strong password (avoid / @ " and spaces)
#   jwt_secret_key    openssl rand -hex 32
#   anthropic_api_key and/or groq_api_key

terraform init
terraform plan      # review what will be created
terraform apply     # provision the stack

# Build images, run migrations, roll out, and health-check in one step:
bash ../scripts/deploy.sh
```

`deploy.sh` is the normal path for **every** deploy (initial and subsequent): it
runs `terraform apply`, builds and pushes the backend + frontend images to ECR,
runs `alembic upgrade head` as a one-off ECS task, forces a new deployment of all
three services, waits for them to stabilise, and verifies
`https://<domain>/health/detailed` returns `"status":"ok"`. You can run it
without a manual `terraform apply` first — it applies the stack itself.

### Notes on DNS & certificates

On the very first apply, ACM DNS validation and Route53 propagation can take a
few minutes; `aws_acm_certificate_validation` blocks until the certificate is
issued, and `deploy.sh` retries the health check for ~5 minutes to absorb that.

## Cost

The stack is sized for the cheapest viable always-on deployment. Running 24×7 it
is roughly **$100–130/month** (ALB + NAT Gateway + Fargate tasks + RDS + Redis
dominate). See [`COST_ESTIMATE.md`](./COST_ESTIMATE.md) for the line-item
breakdown. Most of the cost is fixed hourly infrastructure, not request volume —
the cheapest way to stop charges is to tear the stack down when not in use.

## Teardown

```bash
bash scripts/teardown.sh   # destroys ALL resources after a confirmation prompt
```

> **Data loss:** the S3 documents bucket (`force_destroy`) and the RDS instance
> (`skip_final_snapshot`) are configured so teardown can complete cleanly — their
> data is **deleted**. See the production-hardening note below before relying on
> this stack for real customer data.

## Production-hardening checklist (deliberate cost/durability trade-offs)

The defaults favour low cost. Before serving real customers, review:

- **RDS**: `multi_az = true`, `deletion_protection = true`,
  `skip_final_snapshot = false`, `backup_retention_period >= 7` (`rds.tf`).
- **ElastiCache**: use a replication group with Multi-AZ failover (`elasticache.tf`).
- **NAT**: one NAT Gateway per AZ for egress HA (`vpc.tf`).
- **S3**: `force_destroy = false` and a data-retention policy (`s3.tf`).
- **State**: migrate from local state to the S3 + DynamoDB remote backend
  (instructions in `main.tf`).

## Security posture (already enforced)

- RDS and ElastiCache live in **private subnets** with `publicly_accessible = false`;
  their security groups accept traffic **only from the ECS tasks' security group**.
- ECS tasks accept traffic **only from the ALB security group** (no `0.0.0.0/0`).
- The ALB security group opens **only 80 and 443** to the internet.
- The ECS **task role** is scoped to this project's S3 bucket plus the two
  Textract actions the app calls — no wildcard/admin permissions. The **execution
  role** can read only `/counseliq/*` SSM parameters.
- All secrets live in SSM SecureStrings and are injected into containers at launch;
  none are baked into images or committed to git.

## Never commit

`*.tfstate`, `*.tfstate.*`, `.terraform/`, and `*.tfvars` are gitignored (root and
`infra/terraform/.gitignore`). Only `terraform.tfvars.example` and
`.terraform.lock.hcl` are tracked.
