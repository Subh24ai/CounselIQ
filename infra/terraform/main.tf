# ===========================================================================
# CounselIQ — Terraform root configuration
#
# Provider, backend, and global data sources. Every resource in this project
# is sized for the CHEAPEST viable option for a low-traffic portfolio/demo
# deployment in ap-south-1 (Mumbai). Cost tradeoffs are documented inline in
# each file; see ../COST_ESTIMATE.md for the consolidated monthly estimate.
# ===========================================================================

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # ---------------------------------------------------------------------------
  # State backend.
  #
  # We use LOCAL state for now (zero cost, simplest for a single operator demo).
  # The state file (terraform.tfstate) is gitignored because it can contain
  # sensitive values (e.g. the RDS password).
  #
  # To migrate to a remote S3 backend later (recommended once more than one
  # person touches this, or for CI), create an S3 bucket + DynamoDB lock table
  # out-of-band, then replace the block below with:
  #
  #   backend "s3" {
  #     bucket         = "counseliq-tfstate-<unique-suffix>"
  #     key            = "global/terraform.tfstate"
  #     region         = "ap-south-1"
  #     dynamodb_table = "counseliq-tflock"
  #     encrypt        = true
  #   }
  #
  # and run `terraform init -migrate-state`. The S3 bucket (~pennies/month) and
  # DynamoDB on-demand lock table (~free at this volume) are negligible cost.
  # ---------------------------------------------------------------------------
  backend "local" {}
}

provider "aws" {
  region = var.aws_region

  # Tags applied to every taggable resource for cost allocation / cleanup.
  default_tags {
    tags = {
      Project   = "CounselIQ"
      ManagedBy = "Terraform"
      Env       = var.environment
    }
  }
}

# Real (non-clustered) AZs available in the region; we pick the first
# `az_count` of them for subnet placement.
data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  azs         = slice(data.aws_availability_zones.available.names, 0, var.az_count)
}
