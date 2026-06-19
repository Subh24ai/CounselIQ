# ===========================================================================
# Application Load Balancer — single public entry point for the whole app.
#
# COST NOTE: An ALB costs ~$0.0225/hr base (~$16/month in ap-south-1) plus LCU
# (Load Balancer Capacity Unit) charges that stay near zero at demo traffic.
# One ALB fronts BOTH the frontend and the backend via path-based routing,
# which is cheaper and simpler than running two load balancers.
#
# Routing:
#   /api/*, /health*, /ws/*, /docs, /redoc, /openapi.json  -> backend  (:8000)
#   everything else                                         -> frontend (:3000)
#
# TLS: an HTTPS:443 listener terminates TLS using the ACM certificate in acm.tf
# (modern TLS 1.3 policy). The HTTP:80 listener does no forwarding — it issues a
# permanent 301 redirect to HTTPS so all real traffic is encrypted end-to-user.
# ===========================================================================

resource "aws_lb" "main" {
  name               = "${local.name_prefix}-alb"
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  # Demo: allow `terraform destroy` to remove the ALB.
  enable_deletion_protection = false

  tags = { Name = "${local.name_prefix}-alb" }
}

# --- Target groups (target_type = ip, required for Fargate awsvpc) ----------
resource "aws_lb_target_group" "backend" {
  name        = "${local.name_prefix}-backend"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  # Faster target deregistration on redeploys (default 300s) — small UX win,
  # no cost impact.
  deregistration_delay = 30

  tags = { Name = "${local.name_prefix}-backend-tg" }
}

resource "aws_lb_target_group" "frontend" {
  name        = "${local.name_prefix}-frontend"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/"
    matcher             = "200-399" # Next.js may redirect the root
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  deregistration_delay = 30

  tags = { Name = "${local.name_prefix}-frontend-tg" }
}

# --- Listener: HTTPS:443, terminates TLS, default to the frontend ----------
# certificate_arn comes from the *validation* resource (not the cert directly)
# so the listener is only created once ACM has ISSUED the certificate.
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.main.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }
}

# --- Rule: route API/health/websocket/docs traffic to the backend ----------
resource "aws_lb_listener_rule" "backend" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/api/*", "/health", "/health/*", "/ws/*", "/docs", "/redoc", "/openapi.json"]
    }
  }
}

# --- Listener: HTTP:80, permanent redirect to HTTPS ------------------------
# No targets are served over plaintext HTTP; every request is bounced to 443.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      protocol    = "HTTPS"
      port        = "443"
      status_code = "HTTP_301"
    }
  }
}
