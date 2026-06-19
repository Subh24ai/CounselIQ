# CI/CD Secrets

GitHub repository secrets required by `.github/workflows/ci.yml`. This file
documents **what** is needed and why — never commit the actual values.

Set them under **Settings → Secrets and variables → Actions → New repository
secret** (or scope the AWS/runtime ones to the `production` environment, which
the deploy job uses).

| Secret | Used by | Purpose |
| ------ | ------- | ------- |
| `AWS_ACCESS_KEY_ID` | deploy | Access key for the dedicated CI/CD IAM user (ECR + ECS + iam:PassRole). |
| `AWS_SECRET_ACCESS_KEY` | deploy | Secret for the same IAM user. |
| `GROQ_API_KEY` | backend-ci | Satisfies the startup config validator (≥1 LLM key). Tests mock LLM calls, so any non-empty value works; the workflow falls back to a dummy if unset. |
| `NEXT_PUBLIC_API_URL` | deploy | Production API URL baked into the frontend image, e.g. `https://app.counseliq.in`. |
| `NEXT_PUBLIC_WS_URL` | deploy | Production WebSocket URL, e.g. `wss://app.counseliq.in`. |
| `DOMAIN_NAME` | deploy | Domain the post-deploy HTTPS health check hits, e.g. `app.counseliq.in`. |

> The frontend and backend are served on one ALB under a single domain, so
> `NEXT_PUBLIC_API_URL` and `DOMAIN_NAME` are typically the same host (the
> backend lives under `/api`, `/ws`, `/health`). Use `wss://` for the WS URL.

## CI/CD IAM user

Create a **dedicated IAM user** for CI — **never** root account keys. Attach a
policy granting only the permissions the deploy job uses:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrAuth",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "EcrPushPull",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage"
      ],
      "Resource": [
        "arn:aws:ecr:ap-south-1:<ACCOUNT_ID>:repository/counseliq-backend",
        "arn:aws:ecr:ap-south-1:<ACCOUNT_ID>:repository/counseliq-frontend"
      ]
    },
    {
      "Sid": "EcsDeploy",
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeTaskDefinition",
        "ecs:RegisterTaskDefinition",
        "ecs:UpdateService",
        "ecs:DescribeServices",
        "ecs:RunTask",
        "ecs:DescribeTasks"
      ],
      "Resource": "*"
    },
    {
      "Sid": "PassEcsRoles",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::<ACCOUNT_ID>:role/counseliq-production-ecs-exec",
        "arn:aws:iam::<ACCOUNT_ID>:role/counseliq-production-ecs-task"
      ]
    },
    {
      "Sid": "MigrationTaskLogs",
      "Effect": "Allow",
      "Action": ["logs:GetLogEvents"],
      "Resource": "arn:aws:logs:ap-south-1:<ACCOUNT_ID>:log-group:/ecs/counseliq-production/*"
    }
  ]
}
```

Notes:
- `iam:PassRole` is scoped to **both** ECS roles (`*-ecs-exec` and `*-ecs-task`)
  because `RegisterTaskDefinition` carries both.
- `ecs:*` actions don't support resource-level scoping cleanly across
  Register/Run/Update for our use, so they're `*`; the blast radius is bounded
  by the dedicated user having no other permissions.
- `RegisterTaskDefinition` returns the new revision the deploy then activates;
  the CI user cannot read SSM secrets (the **task execution role** does that at
  container launch), so no SSM permission is granted here.
