import logging
import re
from datetime import datetime, timezone
from typing import Optional

from app.domain.model import Radicado
from app.domain.ports import RadicadoRepository, SecretProvider

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300
MAX_SEARCH_RESULTS = 50


class MongoDBRadicadoRepository(RadicadoRepository):

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
        if self._client is not None:
            return self._client

        from pymongo import MongoClient

        uri = self._secret_provider.get_secret(self._secret_name)
        self._client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        return self._client

    def _get_db(self):
        return self._get_client()[self._database]

    def _get_collection(self, juzgado: str):
        return self._get_db()[juzgado]

    def _get_collection_names_cached(self) -> list[str]:
        now = datetime.now(timezone.utc)
        if self._collection_names_cache and self._collection_cache_ts:
            if (now - self._collection_cache_ts).total_seconds() < CACHE_TTL_SECONDS:
                return self._collection_names_cache

        db = self._get_db()
        self._collection_names_cache = sorted(db.list_collection_names())
        self._collection_cache_ts = now
        return self._collection_names_cache

    def _docs_to_radicados(self, docs: list, juzgado: Optional[str] = None) -> list[Radicado]:
        results = []
        for doc in docs:
            radicado = Radicado(
                numero=str(doc.get("numero", "")),
                ano_estado=str(doc.get("ano_estado", "")),
                relacion=doc.get("relacion", ""),
                tipo=doc.get("tipo", ""),
                radicado=doc.get("radicado", ""),
            )
            if juzgado:
                radicado.juzgado = juzgado
            results.append(radicado)
        return results

    def list_juzgados(self) -> list[str]:
        return self._get_collection_names_cached()

    def search_radicado(self, juzgado: Optional[str], query: str) -> list[Radicado]:
        normalized = query.strip()
        normalized = re.sub(r"\s*-\s*", "-", normalized)
        normalized = re.sub(r"\s+", "", normalized)

        patterns = [re.escape(normalized)]

        if "-" in normalized:
            parts = normalized.split("-", 1)
            if len(parts) == 2 and parts[1].isdigit():
                num_part = parts[1]
                for width in range(len(num_part) + 1, len(num_part) + 4):
                    padded = num_part.zfill(width)
                    patterns.append(re.escape(f"{parts[0]}-{padded}"))

        or_conditions = []
        for pattern in patterns:
            or_conditions.append({"numero": {"$regex": pattern, "$options": "i"}})
            or_conditions.append({"radicado": {"$regex": pattern, "$options": "i"}})

        mongo_query = {"$or": or_conditions}

        if juzgado:
            collection_names = self._get_collection_names_cached()
            if juzgado not in collection_names:
                return []
            collection = self._get_collection(juzgado)
            docs = list(collection.find(mongo_query, {"_id": 0}).limit(MAX_SEARCH_RESULTS))
            return self._docs_to_radicados(docs, juzgado)

        all_results = []
        for col_name in self._get_collection_names_cached():
            collection = self._get_collection(col_name)
            docs = list(collection.find(mongo_query, {"_id": 0}).limit(MAX_SEARCH_RESULTS))
            all_results.extend(self._docs_to_radicados(docs, col_name))
            if len(all_results) >= MAX_SEARCH_RESULTS:
                break

        return all_results[:MAX_SEARCH_RESULTS]

    def search_by_name(self, juzgado: Optional[str], name: str) -> list[Radicado]:
        safe_name = re.escape(name.strip())
        mongo_query = {"relacion": {"$regex": safe_name, "$options": "i"}}

        if juzgado:
            collection_names = self._get_collection_names_cached()
            if juzgado not in collection_names:
                return []
            collection = self._get_collection(juzgado)
            docs = list(collection.find(mongo_query, {"_id": 0}).limit(MAX_SEARCH_RESULTS))
            return self._docs_to_radicados(docs, juzgado)

        all_results = []
        for col_name in self._get_collection_names_cached():
            collection = self._get_collection(col_name)
            docs = list(collection.find(mongo_query, {"_id": 0}).limit(MAX_SEARCH_RESULTS))
            all_results.extend(self._docs_to_radicados(docs, col_name))
            if len(all_results) >= MAX_SEARCH_RESULTS:
                break

        return all_results[:MAX_SEARCH_RESULTS]

    def get_radicados_sample(self, juzgado: str, limit: int = 50) -> list[Radicado]:
        collection_names = self._get_collection_names_cached()
        if juzgado not in collection_names:
            return []

        collection = self._get_collection(juzgado)
        docs = list(collection.find({}, {"_id": 0}).limit(limit))
        return self._docs_to_radicados(docs, juzgado)

    def count_radicados(self, juzgado: str) -> int:
        collection_names = self._get_collection_names_cached()
        if juzgado not in collection_names:
            return 0

        collection = self._get_collection(juzgado)
        return collection.count_documents({})

    def get_all_radicados(self) -> list[Radicado]:
        all_radicados = []
        for col_name in self._get_collection_names_cached():
            collection = self._get_collection(col_name)
            docs = list(collection.find({}, {"_id": 0}))
            all_radicados.extend(self._docs_to_radicados(docs, col_name))
        return all_radicados
