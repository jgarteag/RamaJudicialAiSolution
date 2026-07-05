"""
Lambda handler - Rama Judicial AI Assistant
Integrates with Amazon Bedrock (Claude Haiku 4.5) for intelligent responses
about Colombian judicial processes.
"""

import json
import os
import uuid
from datetime import datetime, timezone

import boto3

# Configuration
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
BEDROCK_REGION = os.environ.get("AWS_BEDROCK_REGION", "us-east-1")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
MAX_TOKENS = 1024

# System prompt for judicial assistant
SYSTEM_PROMPT = """Eres un asistente especializado en el sistema judicial colombiano. Tu rol es ayudar a los ciudadanos a entender y consultar información sobre procesos judiciales en Colombia.

Tus capacidades:
- Explicar conceptos del sistema judicial colombiano (radicados, despachos, tipos de procesos)
- Orientar sobre cómo consultar el estado de un proceso
- Explicar la estructura de la Rama Judicial (juzgados, tribunales, altas cortes)
- Aclarar términos jurídicos en lenguaje sencillo
- Informar sobre los pasos generales de un proceso judicial

Reglas:
- Responde siempre en español
- Sé conciso pero completo (máximo 3-4 párrafos)
- Si no tienes información específica sobre un radicado, indica que actualmente no tienes acceso a la base de datos de consulta en línea, pero orienta al usuario sobre cómo consultar
- No inventes números de radicado, fechas ni estados de procesos específicos
- Si te preguntan algo fuera del ámbito judicial colombiano, indica amablemente que solo puedes ayudar con temas judiciales
- Usa un tono profesional pero accesible"""

# Initialize Bedrock client (reused across invocations)
bedrock_client = None


def get_bedrock_client():
    """Lazy initialization of Bedrock client for Lambda cold start optimization."""
    global bedrock_client
    if bedrock_client is None:
        bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=BEDROCK_REGION,
        )
    return bedrock_client


def invoke_bedrock(message, conversation_history=None):
    """
    Invoke Bedrock with the user message and optional conversation history.
    Returns the assistant's response text.
    """
    client = get_bedrock_client()

    # Build messages array with conversation history
    messages = []
    if conversation_history:
        for msg in conversation_history[-10:]:  # Keep last 10 messages for context
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

    # Add current user message
    messages.append({
        "role": "user",
        "content": message,
    })

    # Invoke Bedrock
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": messages,
    })

    response = client.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    response_body = json.loads(response["body"].read())

    # Extract text from response
    content = response_body.get("content", [])
    if content and content[0].get("type") == "text":
        return content[0]["text"]

    return "No pude generar una respuesta. Por favor intenta de nuevo."


def lambda_handler(event, context):
    """Main Lambda handler for API Gateway HTTP API v2."""
    request_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    # Parse HTTP method and path
    route_key = event.get("routeKey", "")
    http_method = event.get("requestContext", {}).get("http", {}).get("method", "")

    # Health check endpoint
    if route_key == "GET /api/health" or (http_method == "GET" and "/health" in event.get("rawPath", "")):
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "healthy",
                "service": "rama-judicial-ai",
                "environment": ENVIRONMENT,
                "model": BEDROCK_MODEL_ID,
                "timestamp": timestamp,
                "request_id": request_id,
            }),
        }

    # Chat endpoint
    if route_key == "POST /api/chat" or (http_method == "POST" and "/chat" in event.get("rawPath", "")):
        try:
            # Parse request body
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

            # Invoke Bedrock
            ai_response = invoke_bedrock(message, conversation_history)

            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "response": ai_response,
                    "request_id": request_id,
                    "timestamp": timestamp,
                    "model": BEDROCK_MODEL_ID,
                }),
            }

        except boto3.exceptions.Boto3Error as e:
            print(f"Bedrock error: {str(e)}")
            return {
                "statusCode": 503,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "error": "El servicio de IA no está disponible temporalmente. Intenta de nuevo.",
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

    # Not found
    return {
        "statusCode": 404,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "error": "Endpoint no encontrado",
            "request_id": request_id,
        }),
    }
