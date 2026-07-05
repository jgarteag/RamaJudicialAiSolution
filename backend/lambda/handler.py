"""
Lambda handler - Rama Judicial AI Assistant
- POST /api/chat: conversational AI about judicial topics
- POST /api/upload: upload PDF, extract text, search radicados in MongoDB
- GET /api/health: health check
- GET /api/juzgados: list available juzgados from MongoDB

Config (prompt, model, params) from DynamoDB.
MongoDB connection string from Secrets Manager (cached).
"""

import base64
import io
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
MONGODB_SECRET_NAME = os.environ.get("MONGODB_SECRET_NAME", "")

# Defaults for agent config
DEFAULT_CONFIG = {
    "modelId": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "maxTokens": 1024,
    "temperature": 0.7,
    "systemPrompt": (
        "Eres un asistente especializado en el sistema judicial colombiano. "
        "Responde en español, de forma concisa y profesional."
    ),
}

# ─── Caching ─────────────────────────────────────────────────────────────────
_agent_config_cache = None
_config_cache_ts = None
_mongodb_uri_cache = None
_mongo_client_cache = None
CACHE_TTL_SECONDS = 300  # 5 min

# Lazy clients
_bedrock_client = None
_dynamodb_client = None
_secrets_client = None


def get_bedrock_client(region="us-east-1"):
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime", region_name=region)
    return _bedrock_client


def get_dynamodb_client():
    global _dynamodb_client
    if _dynamodb_client is None:
        _dynamodb_client = boto3.resource("dynamodb")
    return _dynamodb_client


def get_secrets_client():
    global _secrets_client
    if _secrets_client is None:
        _secrets_client = boto3.client("secretsmanager")
    return _secrets_client


# ─── Secrets Manager (cached) ────────────────────────────────────────────────

def get_mongodb_uri():
    """Get MongoDB URI from Secrets Manager. Cached for container lifetime."""
    global _mongodb_uri_cache
    if _mongodb_uri_cache is not None:
        return _mongodb_uri_cache

    if not MONGODB_SECRET_NAME:
        raise ValueError("MONGODB_SECRET_NAME not configured")

    client = get_secrets_client()
    response = client.get_secret_value(SecretId=MONGODB_SECRET_NAME)
    _mongodb_uri_cache = response["SecretString"]
    print("MongoDB URI loaded from Secrets Manager (cached)")
    return _mongodb_uri_cache


# ─── MongoDB (connection cached) ─────────────────────────────────────────────

def get_mongo_client():
    """Get MongoDB client. Cached for container lifetime (warm starts reuse)."""
    global _mongo_client_cache
    if _mongo_client_cache is not None:
        return _mongo_client_cache

    from pymongo import MongoClient

    uri = get_mongodb_uri()
    _mongo_client_cache = MongoClient(uri, serverSelectionTimeoutMS=5000)
    print("MongoDB client created (cached)")
    return _mongo_client_cache


def list_juzgados():
    """List all juzgados (collections) from MongoDB."""
    client = get_mongo_client()
    db = client["dbestados"]
    return db.list_collection_names()


def search_radicados_in_text(juzgado_name, text):
    """Search for radicados of a juzgado that appear in the given text."""
    client = get_mongo_client()
    db = client["dbestados"]

    if juzgado_name not in db.list_collection_names():
        return []

    collection = db[juzgado_name]
    radicados = list(collection.find({}, {"_id": 0}))

    encontrados = []
    for rad in radicados:
        numero = rad.get("numero", "")
        radicado_full = rad.get("radicado", "")

        # Search by numero or full radicado in PDF text
        if numero and numero in text:
            idx = text.find(numero)
            contexto = text[max(0, idx - 60):min(len(text), idx + len(numero) + 60)]
            encontrados.append({**rad, "contexto": contexto.strip()})
        elif radicado_full and radicado_full in text:
            idx = text.find(radicado_full)
            contexto = text[max(0, idx - 60):min(len(text), idx + len(radicado_full) + 60)]
            encontrados.append({**rad, "contexto": contexto.strip()})

    return encontrados


def search_all_juzgados(text):
    """Search across ALL juzgados for matches in text."""
    client = get_mongo_client()
    db = client["dbestados"]
    all_results = []

    for collection_name in db.list_collection_names():
        matches = search_radicados_in_text(collection_name, text)
        for match in matches:
            match["juzgado"] = collection_name
        all_results.extend(matches)

    return all_results


# ─── PDF Processing ──────────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_bytes):
    """Extract text from PDF bytes using PyPDF2."""
    from PyPDF2 import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text


# ─── Agent Config (DynamoDB cached) ──────────────────────────────────────────

def load_agent_config():
    """Load agent config from DynamoDB with TTL cache."""
    global _agent_config_cache, _config_cache_ts

    now = datetime.now(timezone.utc)
    if _agent_config_cache and _config_cache_ts:
        if (now - _config_cache_ts).total_seconds() < CACHE_TTL_SECONDS:
            return _agent_config_cache

    if not AGENT_CONFIG_TABLE:
        _agent_config_cache = DEFAULT_CONFIG
        _config_cache_ts = now
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
        else:
            _agent_config_cache = DEFAULT_CONFIG
        _config_cache_ts = now
    except ClientError:
        _agent_config_cache = DEFAULT_CONFIG
        _config_cache_ts = now

    return _agent_config_cache


# ─── Bedrock Invocation ──────────────────────────────────────────────────────

def invoke_bedrock(message, conversation_history=None, extra_context=None):
    """Invoke Bedrock with agent config."""
    config = load_agent_config()
    client = get_bedrock_client(config.get("bedrockRegion", "us-east-1"))

    system_prompt = config["systemPrompt"]
    if extra_context:
        system_prompt += f"\n\nContexto adicional:\n{extra_context}"

    messages = []
    if conversation_history:
        for msg in conversation_history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": message})

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": config["maxTokens"],
        "temperature": config["temperature"],
        "system": system_prompt,
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

    return "No pude generar una respuesta.", config["modelId"]


# ─── Response helpers ────────────────────────────────────────────────────────

def success(body):
    return {"statusCode": 200, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body, ensure_ascii=False)}


def error(status, message, request_id=""):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps({"error": message, "request_id": request_id}, ensure_ascii=False)}


# ─── Main Handler ────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    request_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    route_key = event.get("routeKey", "")
    http_method = event.get("requestContext", {}).get("http", {}).get("method", "")
    raw_path = event.get("rawPath", "")

    # ── Health ───────────────────────────────────────────────────────────────
    if "health" in raw_path and http_method == "GET":
        config = load_agent_config()
        return success({
            "status": "healthy",
            "service": "rama-judicial-ai",
            "environment": ENVIRONMENT,
            "agentId": AGENT_ID,
            "model": config["modelId"],
            "timestamp": timestamp,
        })

    # ── List Juzgados ────────────────────────────────────────────────────────
    if "juzgados" in raw_path and http_method == "GET":
        try:
            juzgados = list_juzgados()
            return success({"juzgados": juzgados, "total": len(juzgados)})
        except Exception as e:
            print(f"MongoDB error: {e}")
            return error(503, "No se pudo conectar a la base de datos", request_id)

    # ── Upload PDF ───────────────────────────────────────────────────────────
    if "upload" in raw_path and http_method == "POST":
        try:
            body = json.loads(event.get("body", "{}"))
            pdf_base64 = body.get("file", "")
            juzgado = body.get("juzgado", "")  # Optional: search specific juzgado

            if not pdf_base64:
                return error(400, "El campo 'file' (base64) es requerido", request_id)

            # Decode PDF
            pdf_bytes = base64.b64decode(pdf_base64)
            pdf_text = extract_text_from_pdf(pdf_bytes)

            if not pdf_text.strip():
                return error(400, "No se pudo extraer texto del PDF", request_id)

            # Search radicados
            if juzgado:
                encontrados = search_radicados_in_text(juzgado, pdf_text)
                for e in encontrados:
                    e["juzgado"] = juzgado
            else:
                encontrados = search_all_juzgados(pdf_text)

            # Generate AI analysis
            if encontrados:
                resumen_matches = "\n".join([
                    f"- Radicado {r['radicado']} ({r.get('relacion', 'N/A')}) "
                    f"del juzgado {r.get('juzgado', 'N/A')}, año {r.get('ano_estado', '?')}"
                    for r in encontrados
                ])
                ai_prompt = (
                    f"Encontré {len(encontrados)} radicados en el PDF del usuario que coinciden "
                    f"con los estados judiciales registrados:\n{resumen_matches}\n\n"
                    f"Genera un resumen claro para el usuario indicando qué radicados se encontraron, "
                    f"de qué juzgado son y qué significan. Sé conciso."
                )
            else:
                ai_prompt = (
                    "No encontré coincidencias de radicados en el PDF con los estados judiciales "
                    "registrados. Indica al usuario que no se encontraron coincidencias y sugiere "
                    "que verifique el juzgado o que los radicados del PDF no están en el sistema."
                )

            ai_response, model = invoke_bedrock(ai_prompt)

            return success({
                "response": ai_response,
                "matches": encontrados,
                "total_matches": len(encontrados),
                "pdf_pages": len(pdf_text.split("\n\n")),
                "request_id": request_id,
                "timestamp": timestamp,
                "model": model,
            })

        except (ValueError, base64.binascii.Error) as e:
            return error(400, f"Error procesando el PDF: {str(e)}", request_id)
        except Exception as e:
            print(f"Upload error: {e}")
            return error(500, "Error procesando el archivo", request_id)

    # ── Chat ─────────────────────────────────────────────────────────────────
    if "chat" in raw_path and http_method == "POST":
        try:
            body = json.loads(event.get("body", "{}"))
            message = body.get("message", "").strip()
            conversation_history = body.get("history", [])

            if not message:
                return error(400, "El campo 'message' es requerido", request_id)

            ai_response, model = invoke_bedrock(message, conversation_history)

            return success({
                "response": ai_response,
                "request_id": request_id,
                "timestamp": timestamp,
                "model": model,
            })

        except ClientError as e:
            print(f"AWS error: {e}")
            return error(503, "El servicio de IA no está disponible temporalmente.", request_id)
        except Exception as e:
            print(f"Error: {e}")
            return error(500, "Error interno del servidor", request_id)

    # ── Not Found ────────────────────────────────────────────────────────────
    return error(404, "Endpoint no encontrado", request_id)
