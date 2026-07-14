"""Ports define abstract interfaces for external communication.

Ports enforce the separation between the domain logic and the adapters.
The domain ONLY communicates with the outside world through these ports.
"""

from abc import ABC, abstractmethod
from typing import Optional

from app.domain.model import AgentConfig, Radicado


class RadicadoRepository(ABC):
    """Port for accessing judicial case records (radicados)."""

    @abstractmethod
    def list_juzgados(self) -> list[str]:
        """Return all available juzgado collection names."""
        ...

    @abstractmethod
    def search_by_candidates(self, juzgado: str, candidates: list[str]) -> list[Radicado]:
        """Search for radicados matching candidate numbers in a specific juzgado."""
        ...

    @abstractmethod
    def get_radicados_sample(self, juzgado: str, limit: int = 50) -> list[Radicado]:
        """Get a sample of radicados from a juzgado for context."""
        ...

    @abstractmethod
    def count_radicados(self, juzgado: str) -> int:
        """Count total radicados in a juzgado."""
        ...


class AIService(ABC):
    """Port for AI/LLM invocation."""

    @abstractmethod
    def invoke(
        self,
        message: str,
        system_prompt: str,
        config: AgentConfig,
        conversation_history: Optional[list] = None,
    ) -> tuple[str, str]:
        """Invoke the AI model. Returns (response_text, model_id)."""
        ...


class ConfigRepository(ABC):
    """Port for retrieving agent configuration."""

    @abstractmethod
    def get_agent_config(self, agent_id: str) -> AgentConfig:
        """Retrieve agent configuration."""
        ...


class SecretProvider(ABC):
    """Port for retrieving secrets."""

    @abstractmethod
    def get_secret(self, secret_name: str) -> str:
        """Retrieve a secret value by name."""
        ...
