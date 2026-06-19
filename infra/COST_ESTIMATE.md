# CounselIQ — AWS Monthly Cost Estimate

Estimate for the **minimal-cost** Terraform stack in `infra/terraform/`, running
**continuously** in **ap-south-1 (Mumbai)** at demo traffic (≈ one task per
service, low request volume).

> **This is NOT free-tier eligible at this scale.** A db.t4g.micro / single ALB /
> NAT Gateway setup runs around **$100–130/month if left on 24×7**. The cheapest
> way to cut the bill to ~$0 is `infra/scripts/teardown.sh` when you're not
> actively demoing — most of the cost is fixed hourly infrastructure, not usage.

All figures are **approximate** on-demand prices and should be confirmed with the
[AWS Pricing Calculator](https://calculator.aws/). Rates drift and vary by AZ.

---

## Line items

| Resource | Spec | Est. $/month | Notes |
|---|---|---:|---|
| **NAT Gateway** | 1 shared (not per-AZ) | **$33–40** | ~$0.045/hr (~$33) + ~$0.045/GB data processing. **Single biggest single-resource cost.** |
| **Application Load Balancer** | 1 ALB, HTTP:80 | **$16–20** | ~$0.0225/hr base (~$16) + small LCU charges. Fronts both frontend & backend. |
| **Fargate — backend** | 0.5 vCPU / 1 GB, on-demand ARM64 | **~$18** | User-facing; on-demand so it's never spot-reclaimed. |
| **Fargate — frontend** | 0.25 vCPU / 0.5 GB, on-demand ARM64 | **~$9** | Next.js standalone; lightest task. |
| **Fargate — worker** | 0.5 vCPU / 2 GB, **FARGATE_SPOT** ARM64 | **~$8–13** | Spot ≈ up to 70% off on-demand; async/idempotent work tolerates interruption. |
| **RDS PostgreSQL** | db.t4g.micro, gp3 20 GB, single-AZ | **~$15** | ~$13 instance + ~$2 gp3 storage. 1-day backups. |
| **ElastiCache Redis** | cache.t4g.micro, single node | **~$12** | No replica/failover. |
| **S3** | documents, low volume | **< $1** | SSE-S3 free; IA transition after 30d; S3 Gateway endpoint keeps traffic off NAT (free). |
| **ECR** | 2 repos, last 5 images each | **< $1** | ~$0.10/GB-month; lifecycle policy bounds it. |
| **SSM Parameter Store** | SecureString, Standard tier | **$0** | Genuinely free (vs Secrets Manager ~$0.40/secret/mo). |
| **CloudWatch Logs** | 7-day retention | **< $1** | Container Insights disabled to avoid metric charges. |
| **Data transfer out** | demo traffic | **$1–3** | First 100 GB/mo region-dependent; small here. |
| **TOTAL** | | **≈ $110–130/mo** | Continuous 24×7 operation. |

ARM64 (Graviton) Fargate is the default in this stack (~20% cheaper than x86 and
matches images built on Apple Silicon). Switching to x86 raises the three Fargate
lines by ~20%.

---

## Where the money actually goes

Grouped by share of a ~$120/month bill:

- **Fixed infrastructure overhead — NAT Gateway + ALB ≈ $50/mo (~42%).** These
  are billed per hour **regardless of traffic** and are the defining cost of a
  low-traffic always-on setup. You pay roughly the same at 10 requests/day as at
  10,000. This is the single most important thing to understand about the bill.
- **Compute — Fargate ≈ $35/mo (~30%).** Already minimized via small task sizes,
  ARM64, and putting the worker on Spot.
- **Stateful data — RDS + Redis ≈ $27/mo (~23%).** Single-AZ, smallest nodes.
- **Everything else — S3/ECR/SSM/logs ≈ $3/mo (~5%).**

### Biggest cost driver
The **NAT Gateway is the largest single resource (~$33–40/mo)**, and together
with the **ALB (~$16–20/mo)** these two fixed-overhead resources are the dominant
cost of running this demo continuously. They cannot be meaningfully reduced while
keeping a "real" private-subnet + load-balanced architecture.

---

## How to reduce or eliminate cost

1. **Tear down when idle** — `infra/scripts/teardown.sh`. Because the bill is
   mostly fixed hourly cost, destroying the stack between demos is by far the
   biggest saving (→ ~$0). State is local; re-running `deploy.sh` recreates it.
2. **Stop tasks, keep data** — scale all three ECS services to `desired_count = 0`
   to drop the ~$35 Fargate compute while keeping RDS/Redis/data intact. (NAT +
   ALB still bill.)
3. **Drop the NAT Gateway entirely** (advanced) — if you add Interface VPC
   endpoints for ECR/SSM/CloudWatch/Secrets and run tasks without egress, you can
   remove the NAT. But ~4 interface endpoints at ~$7/mo each (~$28) roughly match
   the single NAT's cost, so it only wins if you also need them for other reasons.
4. **For real production** (out of scope here, noted for honesty): you'd add
   multi-AZ RDS, a NAT per AZ, a Redis replica, HTTPS/ACM, deletion protection,
   and longer backups — each of which increases cost beyond this estimate.
