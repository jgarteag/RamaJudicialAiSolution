"""
Lambda handler - Rama Judicial AI Assistant
- POST /api/chat: conversational AI
- POST /api/upload: upload documents (PDF, DOCX, TXT), search radicados in MongoDB
- GET /api/health: health check
- GET /api/juzgados: list juzgados from MongoDB

Supported formats: PDF, DOCX, DOC, TXT
Config from DynamoDB. MongoDB URI from Secrets Manager (cached).
"""

import base64
import io
import json
import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

# Environment
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
AGENT_ID = os.environ.get("AGENT_ID", "rama-judicial-ai")
AGENT_CONFIG_TABLE = os.environ.get("AGENT_CONFIG_TABLE", "")
MONGODB_SECRET_NAME = os.environ.get("MONGODB_SECRET_NAME", "")

# Defaults
DEFAULT_CONFIG = {
    "modelId": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "maxTokens": 1024,
    "temperature": 0.7,
    "systemPrompt": (
        "Eres un asistente especializado en el sistema judicial colombiano. "
        "Responde en español, de forma concisa y profesional."
    ),
}

# Supported file types
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".text"}

# ─── Caching ─────────────────────────────────────────────────────────────────
_agent_config_cache = None
_config_cache_ts = None
_mongodb_uri_cache = None
_mongo_client_cache = None
CACHE_TTL_SECONDS = 300

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
    global _mongo_client_cache
    if _mongo_client_cache is not None:
        return _mongo_client_cache

    from pymongo import MongoClient

    uri = get_mongodb_uri()
    _mongo_client_cache = MongoClient(uri, serverSelectionTimeoutMS=5000)
    print("MongoDB client created (cached)")
    return _mongo_client_cache


def list_juzgados():
    client = get_mongo_client()
    db = client["dbestados"]
    return sorted(db.list_collection_names())


def search_radicados_in_text(juzgado_name, text):
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
    client = get_mongo_client()
    db = client["dbestados"]
    all_results = []

    for collection_name in db.list_collection_names():
        matches = search_radicados_in_text(collection_name, text)
        for match in matches:
            match["juzgado"] = collection_name
        all_results.extend(matches)

    return all_results


# ─── Document Processing (multi-format) ─────────────────────────────────────

def extract_text_from_pdf(file_bytes):
    from PyPDF2 import PdfReader

    reader = PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text


def extract_text_from_docx(file_bytes):
    from docx import Document

    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

    # Also extract from tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    paragraphs.append(cell.text.strip())

    return "\n".join(paragraphs)


def extract_text_from_txt(file_bytes):
    # Try UTF-8 first, fall back to latin-1
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1")


def extract_text(file_bytes, filename):
    """Extract text from a file based on its extension."""
    ext = os.path.splitext(filename.lower())[1] if filename else ""

    if ext == ".pdf":
        return extract_text_from_pdf(file_bytes)
    elif ext in (".docx", ".doc"):
        return extract_text_from_docx(file_bytes)
    elif ext in (".txt", ".text", ""):
        return extract_text_from_txt(file_bytes)
    else:
        raise ValueError(f"Formato no soportado: {ext}. Usa PDF, DOCX o TXT.")


# ─── Agent Config (DynamoDB cached) ──────────────────────────────────────────

def load_agent_config():
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


# ─── Bedrock ─────────────────────────────────────────────────────────────────

def invoke_bedrock(message, conversation_history=None, extra_context=None):
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


# ─── MongoDB Context for Chat ────────────────────────────────────────────────

# Known juzgado identifiers for detection
JUZGADOS_KEYWORDS = [
    "J1CMIPIALES", "J2CMIPIALES", "J1PF", "J2PF", "J7FCALI",
    "JPMCONTADERO", "JPMCORDOBA", "JPMCUMBAL", "JPMGUACHUCAL",
    "JPMPOTOSI", "JPMPUPIALES",
]


def get_mongo_context(message):
    """
    Detect if user is asking about juzgados or radicados.
    If so, query MongoDB and return data as context for Bedrock.
    """
    msg_upper = message.upper()

    # Check if user mentions a specific juzgado
    mentioned_juzgados = [j for j in JUZGADOS_KEYWORDS if j in msg_upper]

    # Also detect partial mentions
    if not mentioned_juzgados:
        if "IPIALES" in msg_upper and "1" in message:
            mentioned_juzgados = ["J1CMIPIALES"]
        elif "IPIALES" in msg_upper and "2" in message:
            mentioned_juzgados = ["J2CMIPIALES"]
        elif "IPIALES" in msg_upper:
            mentioned_juzgados = ["J1CMIPIALES", "J2CMIPIALES"]
        elif "CALI" in msg_upper:
            mentioned_juzgados = ["J7FCALI"]
        elif "PUPIALES" in msg_upper:
            mentioned_juzgados = ["JPMPUPIALES"]
        elif "CONTADERO" in msg_upper:
            mentioned_juzgados = ["JPMCONTADERO"]
        elif "CORDOBA" in msg_upper or "CÓRDOBA" in msg_upper:
            mentioned_juzgados = ["JPMCORDOBA"]
        elif "CUMBAL" in msg_upper:
            mentioned_juzgados = ["JPMCUMBAL"]
        elif "GUACHUCAL" in msg_upper:
            mentioned_juzgados = ["JPMGUACHUCAL"]
        elif "POTOSI" in msg_upper or "POTOSÍ" in msg_upper:
            mentioned_juzgados = ["JPMPOTOSI"]

    # Check if asking about all juzgados/radicados/estados
    asking_general = any(w in msg_upper for w in [
        "TODOS LOS RADICADO", "TODOS LOS ESTADO", "QUÉ RADICADO", "QUE RADICADO",
        "QUÉ ESTADO", "QUE ESTADO", "CUÁLES RADICADO", "CUALES RADICADO",
        "MUÉSTRAME", "MUESTRAME", "LISTAR", "LISTADO",
    ])

    if not mentioned_juzgados and not asking_general:
        return None

    try:
        client = get_mongo_client()
        db = client["dbestados"]
        context_parts = []

        if mentioned_juzgados:
            for juzgado in mentioned_juzgados:
                if juzgado in db.list_collection_names():
                    docs = list(db[juzgado].find({}, {"_id": 0}).limit(50))
                    if docs:
                        context_parts.append(
                            f"Juzgado {juzgado} ({len(docs)} radicados):\n"
                            + "\n".join([
                                f"  - Radicado: {d.get('radicado','N/A')}, "
                                f"Relación: {d.get('relacion','N/A')}, "
                                f"Año: {d.get('ano_estado','N/A')}"
                                for d in docs
                            ])
                        )
                    else:
                        context_parts.append(f"Juzgado {juzgado}: sin radicados registrados")
        elif asking_general:
            # Show summary of all juzgados with counts
            for col_name in sorted(db.list_collection_names()):
                count = db[col_name].count_documents({})
                if count > 0:
                    docs = list(db[col_name].find({}, {"_id": 0}).limit(5))
                    sample = ", ".join([d.get("radicado", "") for d in docs[:3]])
                    context_parts.append(
                        f"Juzgado {col_name}: {count} radicados (ej: {sample})"
                    )
                else:
                    context_parts.append(f"Juzgado {col_name}: sin radicados")

        if context_parts:
            return "Datos reales de la base de datos:\n" + "\n\n".join(context_parts)

    except Exception as e:
        print(f"MongoDB context error: {e}")

    return None


# ─── Response helpers ────────────────────────────────────────────────────────

def success(body):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def error(status, message, request_id=""):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": message, "request_id": request_id}, ensure_ascii=False),
    }


# ─── Main Handler ────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    request_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

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
            "formats": list(SUPPORTED_EXTENSIONS),
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

    # ── Upload Document ──────────────────────────────────────────────────────
    if "upload" in raw_path and http_method == "POST":
        try:
            body = json.loads(event.get("body", "{}"))
            file_base64 = body.get("file", "")
            filename = body.get("filename", "document.pdf")
            juzgado = body.get("juzgado", "")  # Optional filter

            if not file_base64:
                return error(400, "El campo 'file' (base64) es requerido", request_id)

            # Validate extension
            ext = os.path.splitext(filename.lower())[1]
            if ext and ext not in SUPPORTED_EXTENSIONS:
                return error(
                    400,
                    f"Formato '{ext}' no soportado. Usa: PDF, DOCX, TXT.",
                    request_id,
                )

            # Decode and extract text
            file_bytes = base64.b64decode(file_base64)
            text = extract_text(file_bytes, filename)

            if not text.strip():
                return error(400, "No se pudo extraer texto del documento", request_id)

            # Search radicados
            if juzgado:
                encontrados = search_radicados_in_text(juzgado, text)
                for e_item in encontrados:
                    e_item["juzgado"] = juzgado
            else:
                encontrados = search_all_juzgados(text)

            # AI analysis
            if encontrados:
                resumen = "\n".join([
                    f"- Radicado {r['radicado']} ({r.get('relacion', 'N/A')}) "
                    f"del juzgado {r.get('juzgado', 'N/A')}, año {r.get('ano_estado', '?')}"
                    for r in encontrados
                ])
                ai_prompt = (
                    f"Encontré {len(encontrados)} radicados en el documento '{filename}' "
                    f"que coinciden con estados judiciales registrados:\n{resumen}\n\n"
                    f"Genera un resumen claro para el usuario. Sé conciso y usa formato markdown."
                )
            else:
                ai_prompt = (
                    f"No encontré coincidencias de radicados en el documento '{filename}' "
                    f"{'del juzgado ' + juzgado if juzgado else 'en ningún juzgado'}. "
                    f"Indica al usuario que no se encontraron coincidencias y sugiere verificar."
                )

            ai_response, model = invoke_bedrock(ai_prompt)

            return success({
                "response": ai_response,
                "matches": encontrados,
                "total_matches": len(encontrados),
                "filename": filename,
                "juzgado_filter": juzgado or "todos",
                "request_id": request_id,
                "timestamp": timestamp,
                "model": model,
            })

        except (ValueError, base64.binascii.Error) as e:
            return error(400, str(e), request_id)
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

            # Check if user is asking about specific juzgado/radicados
            extra_context = get_mongo_context(message)

            ai_response, model = invoke_bedrock(message, conversation_history, extra_context)

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
