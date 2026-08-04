"""Domain model entities for Rama Judicial AI."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Radicado:
    """A judicial case record (radicado) entity."""

    numero: str = ""
    ano_estado: str = ""
    relacion: str = ""
    tipo: str = ""
    radicado: str = ""
    juzgado: Optional[str] = None
    source_file: Optional[str] = None
    contexto: Optional[str] = None

    def to_dict(self) -> dict:
        result = {
            "numero": self.numero,
            "ano_estado": self.ano_estado,
            "relacion": self.relacion,
            "tipo": self.tipo,
            "radicado": self.radicado,
        }
        if self.juzgado:
            result["juzgado"] = self.juzgado
        if self.source_file:
            result["source_file"] = self.source_file
        if self.contexto:
            result["contexto"] = self.contexto
        return result


@dataclass
class ToolDefinition:
    """Definition of a tool that the LLM can invoke."""

    name: str
    description: str
    input_schema: dict

    def to_bedrock_format(self) -> dict:
        """Serialize to Bedrock/Claude tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass
class ChatRequest:
    """A chat request from the user."""

    message: str
    conversation_history: list = field(default_factory=list)


@dataclass
class ChatResponse:
    """A chat response from the AI."""

    response: str
    model: str
    request_id: str
    timestamp: str


@dataclass
class UploadResult:
    """Result of processing uploaded files."""

    ai_response: str
    matches: list = field(default_factory=list)
    files_processed: list = field(default_factory=list)
    skipped_files: list = field(default_factory=list)
    model: str = ""
    juzgado_filter: str = "todos"


@dataclass
class AgentConfig:
    """Configuration for the AI agent from DynamoDB."""

    model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    max_tokens: int = 1024
    temperature: float = 0.7
    system_prompt: str = (
        "Eres un asistente especializado en el sistema judicial colombiano. "
        "Responde en español, de forma concisa y profesional."
    )
    bedrock_region: str = "us-east-1"
