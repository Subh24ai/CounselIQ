# ===========================================================================
# IAM roles for ECS (least privilege). Two distinct roles:
#
#   1. execution role — used by the ECS AGENT to pull images, write logs, and
#      read the SSM secrets it injects into the container at launch.
#   2. task role      — assumed by the APPLICATION code at runtime; only S3
#      (this project's bucket) and the two Textract actions the app calls.
#
# No AdministratorAccess, no "Resource": "*" except where the AWS service
# genuinely does not support resource-level permissions (Textract).
# ===========================================================================

data "aws_caller_identity" "current" {}

# Target key of the AWS-managed aws/ssm key, so we can scope kms:Decrypt to it.
data "aws_kms_alias" "ssm" {
  name = "alias/aws/ssm"
}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ---------------------------------------------------------------------------
# Execution role
# ---------------------------------------------------------------------------
resource "aws_iam_role" "ecs_task_execution" {
  name               = "${local.name_prefix}-ecs-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = { Name = "${local.name_prefix}-ecs-exec" }
}

# AWS-managed policy: ECR pull + CloudWatch Logs write. Standard for Fargate.
resource "aws_iam_role_policy_attachment" "ecs_exec_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Custom inline: read ONLY this project's SSM parameters, and decrypt them with
# the aws/ssm key. Scoped to /counseliq/* — no access to any other parameters.
data "aws_iam_policy_document" "ecs_exec_ssm" {
  statement {
    sid       = "ReadProjectSsmParameters"
    actions   = ["ssm:GetParameters", "ssm:GetParameter"]
    resources = ["arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_prefix}/*"]
  }

  statement {
    sid       = "DecryptSsmSecureStrings"
    actions   = ["kms:Decrypt"]
    resources = [data.aws_kms_alias.ssm.target_key_arn]
  }
}

resource "aws_iam_role_policy" "ecs_exec_ssm" {
  name   = "${local.name_prefix}-ssm-read"
  role   = aws_iam_role.ecs_task_execution.id
  policy = data.aws_iam_policy_document.ecs_exec_ssm.json
}

# ---------------------------------------------------------------------------
# Task (runtime) role
# ---------------------------------------------------------------------------
resource "aws_iam_role" "ecs_task" {
  name               = "${local.name_prefix}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = { Name = "${local.name_prefix}-ecs-task" }
}

data "aws_iam_policy_document" "ecs_task_app" {
  # S3: object-level RW on THIS bucket only, plus the bucket-level reads the
  # SDK needs (region lookup, listing).
  statement {
    sid       = "DocumentsBucketObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.documents.arn}/*"]
  }

  statement {
    sid       = "DocumentsBucketList"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.documents.arn]
  }

  # Textract: ONLY the two async text-detection actions the app calls — not the
  # full Textract suite (no analysis/expense/forms APIs). Textract does not
  # support resource-level permissions, so Resource must be "*"; we minimize by
  # restricting the action set instead.
  statement {
    sid = "TextractAsyncTextDetection"
    actions = [
      "textract:StartDocumentTextDetection",
      "textract:GetDocumentTextDetection",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ecs_task_app" {
  name   = "${local.name_prefix}-app"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task_app.json
}
