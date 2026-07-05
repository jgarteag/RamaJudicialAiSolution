"""
Lambda handler - Rama Judicial AI Assistant
Reads agent configuration (prompt, model, params) from DynamoDB.
Integrates with Amazon Bedrock for intelligent responses.
"""

import json
import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

# Environment variables
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
AGENT_ID = os.environ.get("AGENT_ID", "rama-judicial-ai")
AGENT_CONFIG_TABLE = os.environ.get("AGENT_CONFIG_TABLE", "")

# Defaults (used if DynamoDB config not available)
DEFAULT_CONFIG = {
    "modelId": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "maxTokens": 1024,
    "temperature": 0.7,
    "systemPrompt": (
        "Eres un asistente especializado en el sistema judicial colombiano. "
        "Responde en español, de forma concisa y profesional."
    ),
}

# Cache for agent config (reused across invocations in same container)
_agent_config_cache = None
_cache_timestamp = None
CACHE_TTL_SECONDS = 300  # Refresh config every 5 minutes

# Clients (lazy initialized)
_bedrock_client = None
_dynamodb_client = None


def get_dynamodb_client():
    global _dynamodb_client
    if _dynamodb_client is None:
        _dynamodb_client = boto3.resource("dynamodb")
    return _dynamodb_client


def get_bedrock_client(region="us-east-1"):
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime", region_name=region)
    return _bedrock_client


def load_agent_config():
    """
    Load agent config from DynamoDB. Uses in-memory cache with TTL.
    Returns config dict with keys: modelId, maxTokens, temperature, systemPrompt, bedrockRegion
    """
    global _agent_config_cache, _cache_timestamp

    now = datetime.now(timezone.utc)

    # Return cache if still valid
    if _agent_config_cache and _cache_timestamp:
        elapsed = (now - _cache_timestamp).total_seconds()
        if elapsed < CACHE_TTL_SECONDS:
            return _agent_config_cache

    # No table configured, use defaults
    if not AGENT_CONFIG_TABLE:
        print("No AGENT_CONFIG_TABLE set, using defaults")
        _agent_config_cache = DEFAULT_CONFIG
        _cache_timestamp = now
        return _agent_config_cache

    try:
        dynamodb = get_dynamodb_client()
        table = dynamodb.Table(AGENT_CONFIG_TABLE)
        response = table.get_item(Key={"agentId": AGENT_ID})

        if "Item" in response:
            item = response["Item"]
            _agent_config_cache = {
                "modelId": item.get("modelId", DEFAULT_CONFIG["modelId"]),
                "maxTokens": int(item.get("maxTokens", DEFAULT_CONFIG["maxTokens"])),
                "temperature": float(item.get("temperature", DEFAULT_CONFIG["temperature"])),
                "systemPrompt": item.get("systemPrompt", DEFAULT_CONFIG["systemPrompt"]),
                "bedrockRegion": item.get("bedrockRegion", "us-east-1"),
            }
            _cache_timestamp = now
            print(f"Config loaded for agent '{AGENT_ID}': model={_agent_config_cache['modelId']}")
        else:
            print(f"No config found for agentId '{AGENT_ID}', using defaults")
            _agent_config_cache = DEFAULT_CONFIG
            _cache_timestamp = now

    except ClientError as e:
        print(f"DynamoDB error: {e.response['Error']['Message']}, using defaults")
        _agent_config_cache = DEFAULT_CONFIG
        _cache_timestamp = now

    return _agent_config_cache


def invoke_bedrock(message, conversation_history=None):
    """
    Invoke Bedrock with agent config from DynamoDB.
    """
    config = load_agent_config()

    client = get_bedrock_client(config.get("bedrockRegion", "us-east-1"))

    # Build messages array with conversation history
    messages = []
    if conversation_history:
        for msg in conversation_history[-10:]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

    messages.append({"role": "user", "content": message})

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": config["maxTokens"],
        "temperature": config["temperature"],
        "system": config["systemPrompt"],
        "messages": messages,
    })

    response = client.invoke_model(
        modelId=config["modelId"],
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    response_body = json.loads(response["body"].read())

    content = response_body.get("content", [])
    if content and content[0].get("type") == "text":
        return content[0]["text"], config["modelId"]

    return "No pude generar una respuesta. Por favor intenta de nuevo.", config["modelId"]


def lambda_handler(event, context):
    """Main Lambda handler for API Gateway HTTP API v2."""
    request_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    route_key = event.get("routeKey", "")
    http_method = event.get("requestContext", {}).get("http", {}).get("method", "")

    # Health check
    if route_key == "GET /api/health" or (http_method == "GET" and "/health" in event.get("rawPath", "")):
        config = load_agent_config()
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "healthy",
                "service": "rama-judicial-ai",
                "environment": ENVIRONMENT,
                "agentId": AGENT_ID,
                "model": config["modelId"],
                "timestamp": timestamp,
                "request_id": request_id,
            }),
        }

    # Chat endpoint
    if route_key == "POST /api/chat" or (http_method == "POST" and "/chat" in event.get("rawPath", "")):
        try:
            body = json.loads(event.get("body", "{}"))
            message = body.get("message", "").strip()
            conversation_history = body.get("history", [])

            if not message:
                return {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "error": "El campo 'message' es requerido",
                        "request_id": request_id,
                    }),
                }

            ai_response, model_used = invoke_bedrock(message, conversation_history)

            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "response": ai_response,
                    "request_id": request_id,
                    "timestamp": timestamp,
                    "model": model_used,
                }),
            }

        except ClientError as e:
            print(f"AWS error: {str(e)}")
            return {
                "statusCode": 503,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "error": "El servicio de IA no está disponible temporalmente.",
                    "request_id": request_id,
                    "timestamp": timestamp,
                }),
            }
        except Exception as e:
            print(f"Error: {str(e)}")
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "error": "Error interno del servidor",
                    "request_id": request_id,
                    "timestamp": timestamp,
                }),
            }

    return {
        "statusCode": 404,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": "Endpoint no encontrado", "request_id": request_id}),
    }
