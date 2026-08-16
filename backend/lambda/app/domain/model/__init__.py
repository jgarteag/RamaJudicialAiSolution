"""Domain model entities for Rama Judicial AI."""

from dataclasses import dataclass
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
class AgentConfig:
    """Configuration for the AI agent from DynamoDB (all fields required)."""

    model_id: str
    max_tokens: int
    temperature: float
    system_prompt: str
    bedrock_region: str
