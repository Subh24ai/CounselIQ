# ===========================================================================
# ACM TLS certificate for the custom domain (DNS-validated).
#
# REGION: this certificate is created by the default AWS provider, which is
# pinned to var.aws_region (ap-south-1). An ALB requires its certificate to live
# in the SAME region as the load balancer — so this cert MUST be in ap-south-1.
# (The us-east-1 requirement applies only to CloudFront, which this stack does
# not use. Do not move this cert to us-east-1.)
#
# Validation is via DNS records published into the Route53 hosted zone (see
# route53.tf). aws_acm_certificate_validation blocks until the cert is ISSUED,
# so the HTTPS listener that depends on it is never created against a pending
# certificate.
# ===========================================================================

resource "aws_acm_certificate" "main" {
  domain_name       = var.domain_name
  validation_method = "DNS"

  # Replace before destroy so an in-use cert is never removed out from under the
  # ALB listener during a rotation/change.
  lifecycle {
    create_before_destroy = true
  }

  tags = { Name = "${local.name_prefix}-cert" }
}

resource "aws_acm_certificate_validation" "main" {
  certificate_arn         = aws_acm_certificate.main.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}
