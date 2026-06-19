# ===========================================================================
# ECR container registries (one per image).
#
# COST NOTE: ECR charges ~$0.10/GB-month for stored images. The lifecycle
# policy below keeps only the last 5 images per repo so storage cannot creep.
# scan_on_push is FREE (basic scanning) and is good hygiene.
# force_delete=true lets `terraform destroy` remove repos that still contain
# images (so the teardown script works without a manual purge).
# ===========================================================================

locals {
  ecr_repos = {
    backend  = "${var.project_name}-backend"
    frontend = "${var.project_name}-frontend"
  }
}

resource "aws_ecr_repository" "this" {
  for_each = local.ecr_repos

  name                 = each.value
  force_delete         = true
  image_tag_mutability = "MUTABLE" # allows re-pushing the "latest" tag on each deploy

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Name = each.value }
}

# Keep only the 5 most recent images; expire the rest to bound storage cost.
resource "aws_ecr_lifecycle_policy" "this" {
  for_each   = aws_ecr_repository.this
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep only the last 5 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = { type = "expire" }
      }
    ]
  })
}
