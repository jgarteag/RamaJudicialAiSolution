# ============================================
# Módulo: CloudFront Distribution
# CDN para servir el frontend desde S3 (OAC)
# HTTPS por defecto, SPA fallback, cache optimizado
# ============================================

# Origin Access Control - Acceso seguro a S3
resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project_name}-oac-${var.environment}"
  description                       = "OAC para acceso seguro a S3 frontend"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# CloudFront Distribution
resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.project_name} - Frontend (${var.environment})"
  default_root_object = "index.html"
  price_class         = var.price_class
  http_version        = "http2and3"

  # Origin: S3 Bucket
  origin {
    domain_name              = var.s3_bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  # Default Cache Behavior - Archivos estáticos
  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    cache_policy_id            = aws_cloudfront_cache_policy.frontend.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
  }

  # SPA Fallback - Redirige 403/404 a index.html
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  # Restricciones geográficas
  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # Certificado SSL (default CloudFront)
  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = merge(var.tags, {
    Component = "cdn"
  })
}

# Cache Policy optimizada para SPA
resource "aws_cloudfront_cache_policy" "frontend" {
  name        = "${var.project_name}-cache-policy-${var.environment}"
  comment     = "Cache policy para frontend SPA"
  min_ttl     = 0
  default_ttl = 86400    # 1 día
  max_ttl     = 31536000 # 1 año

  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }

    headers_config {
      header_behavior = "none"
    }

    query_strings_config {
      query_string_behavior = "none"
    }

    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true
  }
}

# Response Headers Policy - Security headers
resource "aws_cloudfront_response_headers_policy" "security" {
  name    = "${var.project_name}-security-headers-${var.environment}"
  comment = "Security headers para frontend"

  security_headers_config {
    content_type_options {
      override = true
    }

    frame_options {
      frame_option = "DENY"
      override     = true
    }

    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }

    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      preload                    = true
      override                   = true
    }

    xss_protection {
      mode_block = true
      protection = true
      override   = true
    }
  }
}
