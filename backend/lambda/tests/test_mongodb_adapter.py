"""Tests for MongoDB adapter - new search methods for tool use."""

from unittest.mock import MagicMock, patch

import pytest
from app.adapters.mongodb_adapter import MongoDBRadicadoRepository
from app.domain.ports import SecretProvider


@pytest.fixture
def mock_secret_provider():
    provider = MagicMock(spec=SecretProvider)
    provider.get_secret.return_value = "mongodb+srv://test:test@cluster.mongodb.net"
    return provider


@pytest.fixture
def repo(mock_secret_provider):
    r = MongoDBRadicadoRepository(
        secret_provider=mock_secret_provider,
        secret_name="test-secret",
    )
    # Pre-populate cache to avoid real MongoDB connection
    r._collection_names_cache = ["J1CMIPIALES", "J2CMIPIALES", "JPMCORDOBA"]
    from datetime import datetime, timezone
    r._collection_cache_ts = datetime.now(timezone.utc)
    return r


class TestSearchRadicado:
    """Test flexible radicado search."""

    def test_search_radicado_exact_match(self, repo):
        mock_collection = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.limit.return_value = [
            {"numero": "0421", "ano_estado": 2024, "relacion": "PERSONA",
             "tipo": "J1CMIPIALES", "radicado": "2024-0421"}
        ]
        mock_collection.find.return_value = mock_cursor
        with patch.object(repo, "_get_collection", return_value=mock_collection):
            results = repo.search_radicado("J1CMIPIALES", "0421")

        assert len(results) == 1
        assert results[0].numero == "0421"

    def test_search_radicado_partial_match(self, repo):
        mock_collection = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.limit.return_value = [
            {"numero": "0421", "ano_estado": 2024, "relacion": "PERSONA",
             "tipo": "J1CMIPIALES", "radicado": "2024-0421"}
        ]
        mock_collection.find.return_value = mock_cursor
        with patch.object(repo, "_get_collection", return_value=mock_collection):
            repo.search_radicado("J1CMIPIALES", "2024")

        # Verify regex query was used
        call_args = mock_collection.find.call_args[0][0]
        assert "$or" in call_args

    def test_search_radicado_across_all_juzgados(self, repo):
        mock_collection = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.limit.return_value = [
            {"numero": "0421", "ano_estado": 2024, "relacion": "PERSONA",
             "tipo": "J1CMIPIALES", "radicado": "2024-0421"}
        ]
        mock_collection.find.return_value = mock_cursor

        with patch.object(repo, "_get_collection", return_value=mock_collection):
            results = repo.search_radicado(None, "0421")

        assert len(results) >= 1
        # Should have searched all 3 collections
        assert mock_collection.find.call_count == 3

    def test_search_radicado_invalid_juzgado_returns_empty(self, repo):
        results = repo.search_radicado("INVALID_JUZGADO", "0421")
        assert results == []


class TestSearchByName:
    """Test name-based search."""

    def test_search_by_name_uses_regex(self, repo):
        mock_collection = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.limit.return_value = [
            {"numero": "0421", "ano_estado": 2024,
             "relacion": "MAYRA ALEJANDRA RODRIGUEZ CALDERON",
             "tipo": "J1CMIPIALES", "radicado": "2024-0421"}
        ]
        mock_collection.find.return_value = mock_cursor
        with patch.object(repo, "_get_collection", return_value=mock_collection):
            results = repo.search_by_name("J1CMIPIALES", "RODRIGUEZ")

        assert len(results) == 1
        assert "RODRIGUEZ" in results[0].relacion

    def test_search_by_name_case_insensitive(self, repo):
        mock_collection = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.limit.return_value = [
            {"numero": "0421", "ano_estado": 2024,
             "relacion": "MAYRA ALEJANDRA RODRIGUEZ CALDERON",
             "tipo": "J1CMIPIALES", "radicado": "2024-0421"}
        ]
        mock_collection.find.return_value = mock_cursor
        with patch.object(repo, "_get_collection", return_value=mock_collection):
            repo.search_by_name("J1CMIPIALES", "rodriguez")

        # Verify case-insensitive regex was used
        call_args = mock_collection.find.call_args[0][0]
        assert call_args["relacion"]["$options"] == "i"

    def test_search_by_name_across_all_juzgados(self, repo):
        mock_collection = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.limit.return_value = [
            {"numero": "0421", "ano_estado": 2024,
             "relacion": "PERSONA TEST",
             "tipo": "J1CMIPIALES", "radicado": "2024-0421"}
        ]
        mock_collection.find.return_value = mock_cursor

        with patch.object(repo, "_get_collection", return_value=mock_collection):
            results = repo.search_by_name(None, "PERSONA")

        assert len(results) >= 1
        assert mock_collection.find.call_count == 3

    def test_search_by_name_invalid_juzgado_returns_empty(self, repo):
        results = repo.search_by_name("INVALID_JUZGADO", "TEST")
        assert results == []
