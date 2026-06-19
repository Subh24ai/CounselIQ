# ===========================================================================
# S3 bucket for uploaded legal documents.
#
# COST NOTES:
#   - Versioning DISABLED: versioning keeps every overwrite/delete as a billable
#     object version. Off = no duplicate-storage cost on a demo.
#   - SSE-S3 (AES256): server-side encryption at rest is FREE (unlike SSE-KMS
#     with a customer key, which adds per-request KMS charges).
#   - Lifecycle: transition to STANDARD_IA after 30 days. IA is cheaper per GB
#     for objects that are rarely read after the initial analysis. Minor saving,
#     low risk for low-traffic data.
#   - force_destroy = true: lets `terraform destroy` empty + delete the bucket
#     for the demo teardown. This DELETES all documents on destroy — production
#     should set this false and handle data retention explicitly.
#
# Bucket names are globally unique, so we append a short random suffix.
# ===========================================================================

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "documents" {
  bucket        = "${var.project_name}-documents-${random_id.bucket_suffix.hex}"
  force_destroy = true

  tags = { Name = "${var.project_name}-documents" }
}

# Block ALL public access — documents are private and served via presigned URLs.
resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3, free
    }
  }
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    # Applies to all objects in the bucket.
    filter {}

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    # Clean up incomplete multipart uploads so they don't accrue silent storage.
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
