from abc import ABC, abstractmethod
from typing import Optional

from app.domain.model import Radicado


class RadicadoRepository(ABC):

    @abstractmethod
    def list_juzgados(self) -> list[str]:
        ...

    @abstractmethod
    def search_radicado(self, juzgado: Optional[str], query: str) -> list[Radicado]:
        ...

    @abstractmethod
    def search_by_name(self, juzgado: Optional[str], name: str) -> list[Radicado]:
        ...

    @abstractmethod
    def get_radicados_sample(self, juzgado: str, limit: int = 50) -> list[Radicado]:
        ...

    @abstractmethod
    def count_radicados(self, juzgado: str) -> int:
        ...

    @abstractmethod
    def get_all_radicados(self) -> list[Radicado]:
        ...


class SecretProvider(ABC):

    @abstractmethod
    def get_secret(self, secret_name: str) -> str:
        ...
