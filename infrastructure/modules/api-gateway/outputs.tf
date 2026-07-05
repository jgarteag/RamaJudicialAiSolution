output "api_endpoint" {
  description = "HTTP API endpoint URL"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "api_id" {
  description = "HTTP API ID"
  value       = aws_apigatewayv2_api.main.id
}

output "execution_arn" {
  description = "API Gateway execution ARN"
  value       = aws_apigatewayv2_api.main.execution_arn
}
