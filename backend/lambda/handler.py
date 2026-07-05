"""
Rama Judicial AI - API Lambda Handler
Handles chat requests and health checks.
Prepared for future Bedrock/LLM integration.
"""

import json
import os
from datetime import datetime

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
PROJECT = os.environ.get("PROJECT", "rama-judicial-ai")


def lambda_handler(event, context):
    """Main Lambda handler for API Gateway HTTP API v2."""
    route_key = event.get("routeKey", "")
    http_method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("requestContext", {}).get("http", {}).get("path", "")

    if route_key == "GET /api/health":
        return handle_health(context)
    elif route_key == "POST /api/chat":
        return handle_chat(event, context)
    else:
        return response(404, {"error": "Not found", "path": path})


def handle_health(context):
    """Health check endpoint."""
    return response(200, {
        "status": "healthy",
        "service": PROJECT,
        "environment": ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "request_id": context.aws_request_id,
    })


def handle_chat(event, context):
    """Chat endpoint - echoes for now, will integrate with Bedrock later."""
    try:
        body = json.loads(event.get("body", "{}"))
    except (json.JSONDecodeError, TypeError):
        return response(400, {"error": "Invalid JSON body"})

    message = body.get("message", "").strip()
    if not message:
        return response(400, {"error": "Field 'message' is required"})

    # TODO: Microstack 3 - Replace with Bedrock/LLM call
    ai_response = generate_response(message)

    return response(200, {
        "response": ai_response,
        "request_id": context.aws_request_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    })


def generate_response(message):
    """
    Generate AI response.
    Currently returns contextual echo.
    Will be replaced by Bedrock integration in Microstack 3.
    """
    message_lower = message.lower()

    if any(word in message_lower for word in ["radicado", "proceso", "expediente"]):
        return (
            f"Entiendo que estás consultando sobre un proceso judicial. "
            f"Tu consulta: \"{message}\". "
            f"En la siguiente fase integraremos la búsqueda real en la base de datos "
            f"de la Rama Judicial. Por ahora, confirmo que el sistema está operativo."
        )
    elif any(word in message_lower for word in ["estado", "consulta", "buscar"]):
        return (
            f"Recibí tu consulta: \"{message}\". "
            f"El módulo de IA para búsqueda de estados judiciales está en desarrollo. "
            f"Pronto podrás consultar el estado real de cualquier proceso."
        )
    else:
        return (
            f"Hola, soy el asistente de la Rama Judicial. Recibí: \"{message}\". "
            f"Puedes preguntarme sobre radicados, estados de procesos o expedientes judiciales."
        )


def response(status_code, body):
    """Build HTTP API v2 response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }
