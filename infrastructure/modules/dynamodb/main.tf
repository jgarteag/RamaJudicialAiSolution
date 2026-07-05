# ==============================================================================
# DynamoDB Table - Agent Configuration Store
# PAY_PER_REQUEST = serverless, $0 at rest, ~$1.25/million writes, $0.25/million reads
# Perfect for low-traffic config reads
# ==============================================================================

resource "aws_dynamodb_table" "agent_config" {
  name         = "${var.project_name}-agent-config-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "agentId"

  attribute {
    name = "agentId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false # Not needed for config table in dev
  }

  tags = var.tags
}
