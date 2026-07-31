"""MongoDB adapter - implements RadicadoRepository port.

Handles all communication with MongoDB Atlas for judicial case records.
Connection is cached at module level (Lambda execution context reuse).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from app.domain.model import Radicado
from app.domain.ports import RadicadoRepository, SecretProvider

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300


class MongoDBRadicadoRepository(RadicadoRepository):
    """Concrete MongoDB implementation of the RadicadoRepository port."""

    def __init__(
        self, secret_provider: SecretProvider, secret_name: str, database: str = "dbestados"
    ):
        self._secret_provider = secret_provider
        self._secret_name = secret_name
        self._database = database
        self._client = None
        self._collection_names_cache: Optional[list[str]] = None
        self._collection_cache_ts: Optional[datetime] = None

    def _get_client(self):
        """Get or create MongoDB client (cached across invocations)."""
        if self._client is not None:
            return self._client

        from pymongo import MongoClient

        uri = self._secret_provider.get_secret(self._secret_name)
        self._client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        logger.info("MongoDB client created")
        return self._client

    def _get_db(self):
        """Get the database instance."""
        return self._get_client()[self._database]

    def _get_collection_names_cached(self) -> list[str]:
        """Return cached list of collection names (TTL-based)."""
        now = datetime.now(timezone.utc)
        if self._collection_names_cache and self._collection_cache_ts:
            if (now - self._collection_cache_ts).total_seconds() < CACHE_TTL_SECONDS:
                return self._collection_names_cache

        db = self._get_db()
        self._collection_names_cache = sorted(db.list_collection_names())
        self._collection_cache_ts = now
        logger.info(
            "Collection names refreshed", extra={"count": len(self._collection_names_cache)}
        )
        return self._collection_names_cache

    def list_juzgados(self) -> list[str]:
        """Return all available juzgado collection names."""
        return self._get_collection_names_cached()

    def search_by_candidates(self, juzgado: str, candidates: list[str]) -> list[Radicado]:
        """Search for radicados matching candidate numbers using $in query."""
        collection_names = self._get_collection_names_cached()
        if juzgado not in collection_names:
            return []

        db = self._get_db()
        collection = db[juzgado]

        query = {"$or": [
            {"numero": {"$in": candidates}},
            {"radicado": {"$in": candidates}},
        ]}
        docs = list(collection.find(query, {"_id": 0}))

        logger.info(
            "Radicado search completed",
            extra={"juzgado": juzgado, "candidates": len(candidates), "matches": len(docs)},
        )

        return [
            Radicado(
                numero=doc.get("numero", ""),
                ano_estado=doc.get("ano_estado", ""),
                relacion=doc.get("relacion", ""),
                tipo=doc.get("tipo", ""),
                radicado=doc.get("radicado", ""),
            )
            for doc in docs
        ]

    def get_radicados_sample(self, juzgado: str, limit: int = 50) -> list[Radicado]:
        """Get a sample of radicados from a juzgado."""
        collection_names = self._get_collection_names_cached()
        if juzgado not in collection_names:
            return []

        db = self._get_db()
        docs = list(db[juzgado].find({}, {"_id": 0}).limit(limit))

        return [
            Radicado(
                numero=doc.get("numero", ""),
                ano_estado=doc.get("ano_estado", ""),
                relacion=doc.get("relacion", ""),
                tipo=doc.get("tipo", ""),
                radicado=doc.get("radicado", ""),
            )
            for doc in docs
        ]

    def count_radicados(self, juzgado: str) -> int:
        """Count total radicados in a juzgado."""
        collection_names = self._get_collection_names_cached()
        if juzgado not in collection_names:
            return 0

        db = self._get_db()
        return db[juzgado].count_documents({})
