"""Lambda entrypoint - primary adapter.

This is the thinnest possible layer. It:
1. Parses the HTTP event from API Gateway
2. Wires up the adapters (dependency injection)
3. Delegates to the domain services
4. Returns the HTTP response

No business logic lives here — it's all in app.domain.services.
"""

import io
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from app.adapters.bedrock_adapter import BedrockAIService
from app.adapters.dynamodb_adapter import DynamoDBConfigRepository
from app.adapters.mongodb_adapter import MongoDBRadicadoRepository
from app.adapters.secrets_adapter import SecretsManagerProvider
from app.domain.services import ToolUseChatService

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ─── Environment ─────────────────────────────────────────────────────────────
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
AGENT_ID = os.environ.get("AGENT_ID", "rama-judicial-ai")
AGENT_CONFIG_TABLE = os.environ.get("AGENT_CONFIG_TABLE", "")
MONGODB_SECRET_NAME = os.environ.get("MONGODB_SECRET_NAME", "")

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".text"}

# ─── Adapter singletons (cached across invocations) ─────────────────────────
_secret_provider = None
_radicado_repo = None
_ai_service = None
_config_repo = None


def _get_secret_provider() -> SecretsManagerProvider:
    global _secret_provider
    if _secret_provider is None:
        _secret_provider = SecretsManagerProvider()
    return _secret_provider


def _get_radicado_repo() -> MongoDBRadicadoRepository:
    global _radicado_repo
    if _radicado_repo is None:
        _radicado_repo = MongoDBRadicadoRepository(
            secret_provider=_get_secret_provider(),
            secret_name=MONGODB_SECRET_NAME,
        )
    return _radicado_repo


def _get_ai_service() -> BedrockAIService:
    global _ai_service
    if _ai_service is None:
        _ai_service = BedrockAIService()
    return _ai_service


def _get_config_repo() -> DynamoDBConfigRepository:
    global _config_repo
    if _config_repo is None:
        _config_repo = DynamoDBConfigRepository(table_name=AGENT_CONFIG_TABLE)
    return _config_repo


# ─── Document text extraction (infra concern, stays in entrypoint) ───────────

def extract_text(file_bytes: bytes, filename: str) -> str:
    """Extract text from file based on extension."""
    ext = os.path.splitext(filename.lower())[1] if filename else ""

    if ext == ".pdf":
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text

    elif ext in (".docx", ".doc"):
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        paragraphs.append(cell.text.strip())
        return "\n".join(paragraphs)

    elif ext in (".txt", ".text", ""):
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return file_bytes.decode("latin-1")

    else:
        raise ValueError(f"Formato no soportado: {ext}. Usa PDF, DOCX o TXT.")


# ─── HTTP Response helpers ───────────────────────────────────────────────────

def success(body: dict) -> dict:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def error(status: int, message: str, request_id: str = "") -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": message, "request_id": request_id}, ensure_ascii=False),
    }


# ─── Lambda Handler ──────────────────────────────────────────────────────────

def lambda_handler(event, context):
    """AWS Lambda entry point - thin primary adapter."""
    request_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    http_method = event.get("requestContext", {}).get("http", {}).get("method", "")
    raw_path = event.get("rawPath", "")

    logger.info(
        "Request", extra={"request_id": request_id, "method": http_method, "path": raw_path}
    )

    # ── Health ───────────────────────────────────────────────────────────────
    if "health" in raw_path and http_method == "GET":
        config = _get_config_repo().get_agent_config(AGENT_ID)
        return success({
            "status": "healthy",
            "service": "rama-judicial-ai",
            "environment": ENVIRONMENT,
            "agentId": AGENT_ID,
            "model": config.model_id,
            "formats": list(SUPPORTED_EXTENSIONS),
            "timestamp": timestamp,
        })

    # ── List Juzgados ────────────────────────────────────────────────────────
    if "juzgados" in raw_path and http_method == "GET":
        try:
            juzgados = _get_radicado_repo().list_juzgados()
            return success({"juzgados": juzgados, "total": len(juzgados)})
        except Exception as e:
            logger.error("MongoDB connection failed", extra={"error": str(e)})
            return error(503, "No se pudo conectar a la base de datos", request_id)

    # ── Upload Document ──────────────────────────────────────────────────────
    if "upload" in raw_path and http_method == "POST":
        try:
            body = json.loads(event.get("body", "{}"))
            juzgado = body.get("juzgado", "")

            # Support both single file and multiple files
            files_data = body.get("files", [])
            if not files_data:
                single_file = body.get("file", "")
                single_name = body.get("filename", "document.pdf")
                if single_file:
                    files_data = [{"file": single_file, "filename": single_name}]

            if not files_data:
                return error(
                    400, "Se requiere al menos un archivo (campo 'files' o 'file')", request_id
                )

            # Extract text from all files
            import base64

            all_texts = []
            processed_files = []
            skipped_files = []

            for file_item in files_data:
                file_base64 = file_item.get("file", "")
                filename = file_item.get("filename", "document.pdf")

                if not file_base64:
                    skipped_files.append({"filename": filename, "reason": "Archivo vacío"})
                    continue

                ext = os.path.splitext(filename.lower())[1]
                if ext and ext not in SUPPORTED_EXTENSIONS:
                    skipped_files.append(
                        {"filename": filename, "reason": f"Formato {ext} no soportado"}
                    )
                    continue

                try:
                    file_bytes = base64.b64decode(file_base64)
                    text = extract_text(file_bytes, filename)
                except Exception as e:
                    skipped_files.append(
                        {"filename": filename, "reason": f"Error: {str(e)}"}
                    )
                    continue

                if not text.strip():
                    skipped_files.append(
                        {"filename": filename, "reason": "No se pudo extraer texto"}
                    )
                    continue

                processed_files.append(filename)
                all_texts.append(f"--- Archivo: {filename} ---\n{text}")

            if not processed_files:
                return error(400, "No se pudo extraer texto de ningún archivo", request_id)

            # Build message for the ToolUseChatService
            juzgado_hint = f" en el juzgado {juzgado}" if juzgado else ""
            user_message = (
                f"El usuario subió {len(processed_files)} documento(s). "
                f"Busca coincidencias de radicados{juzgado_hint} en la base de datos."
                f"\n\n" + "\n\n".join(all_texts)
            )

            # Use ToolUseChatService for intelligent search
            chat_svc = ToolUseChatService(
                ai_service=_get_ai_service(),
                config_repo=_get_config_repo(),
                radicado_repo=_get_radicado_repo(),
                agent_id=AGENT_ID,
            )

            ai_response, model = chat_svc.chat(user_message)

            logger.info(
                "Upload processed",
                extra={
                    "request_id": request_id,
                    "files_processed": len(processed_files),
                    "files_skipped": len(skipped_files),
                },
            )

            return success({
                "response": ai_response,
                "files_processed": processed_files,
                "skipped_files": skipped_files,
                "request_id": request_id,
                "timestamp": timestamp,
                "model": model,
            })

        except (ValueError, Exception) as e:
            logger.error("Upload error", extra={"request_id": request_id, "error": str(e)})
            status_code = 400 if isinstance(e, ValueError) else 500
            message = str(e) if isinstance(e, ValueError) else "Error procesando el archivo"
            return error(status_code, message, request_id)

    # ── Chat ─────────────────────────────────────────────────────────────────
    if "chat" in raw_path and http_method == "POST":
        try:
            body = json.loads(event.get("body", "{}"))
            message = body.get("message", "").strip()
            conversation_history = body.get("history", [])

            if not message:
                return error(400, "El campo 'message' es requerido", request_id)

            chat_svc = ToolUseChatService(
                ai_service=_get_ai_service(),
                config_repo=_get_config_repo(),
                radicado_repo=_get_radicado_repo(),
                agent_id=AGENT_ID,
            )

            ai_response, model = chat_svc.chat(message, conversation_history)

            return success({
                "response": ai_response,
                "request_id": request_id,
                "timestamp": timestamp,
                "model": model,
            })

        except Exception as e:
            logger.error("Chat error", extra={"request_id": request_id, "error": str(e)})
            return error(500, "Error interno del servidor", request_id)

    # ── Not Found ────────────────────────────────────────────────────────────
    return error(404, "Endpoint no encontrado", request_id)
