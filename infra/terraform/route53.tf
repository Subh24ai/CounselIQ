# ===========================================================================
# Route53 — DNS validation records for the ACM cert, and the public A-record
# that points the custom domain at the ALB.
#
# Assumes the hosted zone (var.hosted_zone_name, e.g. "counseliq.in") already
# exists and is the authoritative public zone for the domain. We look it up as a
# data source rather than creating it, because the zone's nameservers must be
# registered with your domain registrar out-of-band (a one-time manual step that
# Terraform cannot do).
# ===========================================================================

data "aws_route53_zone" "main" {
  name         = var.hosted_zone_name
  private_zone = false
}

# One validation record per domain on the certificate (just the apex/host here,
# but for_each keeps this correct if SANs are added later).
resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.main.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.main.zone_id
}

# Public alias record: the custom domain -> the ALB. An alias A-record is free
# (no per-query charge like a CNAME) and resolves directly to the ALB.
resource "aws_route53_record" "app" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}
