import base64
import json
from unittest.mock import MagicMock, patch

import pytest
from app.domain.model import Radicado


@pytest.fixture
def mock_repo():
    with patch("app.entrypoints._get_radicado_repo") as mock:
        repo = MagicMock()
        mock.return_value = repo
        yield repo


class TestHealthEndpoint:

    def test_returns_healthy(self):
        from app.entrypoints import lambda_handler

        event = {"requestContext": {"http": {"method": "GET"}}, "rawPath": "/api/health"}

        result = lambda_handler(event, None)

        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["status"] == "healthy"


class TestJuzgadosEndpoint:

    def test_returns_juzgados_list(self, mock_repo):
        from app.entrypoints import lambda_handler

        mock_repo.list_juzgados.return_value = ["J1PF", "J2PF"]
        event = {"requestContext": {"http": {"method": "GET"}}, "rawPath": "/api/juzgados"}

        result = lambda_handler(event, None)

        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["juzgados"] == ["J1PF", "J2PF"]
        assert body["total"] == 2


class TestUploadEndpoint:

    def test_finds_matches_in_uploaded_file(self, mock_repo):
        from app.entrypoints import lambda_handler

        mock_repo.get_all_radicados.return_value = [
            Radicado(
                numero="0421",
                radicado="2024-0421",
                ano_estado="2024",
                relacion="MARIA LOPEZ",
                tipo="J1CMIPIALES",
                juzgado="J1CMIPIALES",
            ),
        ]

        text_content = "Estado del radicado 0421 notificado"
        file_b64 = base64.b64encode(text_content.encode()).decode()

        event = {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": "/api/upload",
            "body": json.dumps({"file": file_b64, "filename": "estados.txt"}),
        }

        result = lambda_handler(event, None)

        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["total_matches"] == 1
        assert body["matches"][0]["numero"] == "0421"
        assert body["matches"][0]["filename"] == "estados.txt"
        assert "estados.txt" in body["response"]

    def test_no_matches_returns_message(self, mock_repo):
        from app.entrypoints import lambda_handler

        mock_repo.get_all_radicados.return_value = [
            Radicado(numero="9999", radicado="2024-9999", juzgado="J1PF"),
        ]

        file_b64 = base64.b64encode(b"Nada relevante aqui").decode()

        event = {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": "/api/upload",
            "body": json.dumps({"file": file_b64, "filename": "vacio.txt"}),
        }

        result = lambda_handler(event, None)

        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert body["total_matches"] == 0
        assert "No se encontraron" in body["response"]

    def test_filters_by_juzgado(self, mock_repo):
        from app.entrypoints import lambda_handler

        mock_repo.get_all_radicados.return_value = [
            Radicado(numero="0421", radicado="2024-0421", juzgado="J1CMIPIALES"),
            Radicado(numero="0211", radicado="2022-00211", juzgado="J1PF"),
        ]

        file_b64 = base64.b64encode(b"0421 y 0211 ambos").decode()

        event = {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": "/api/upload",
            "body": json.dumps({
                "file": file_b64,
                "filename": "doc.txt",
                "juzgado": "J1PF",
            }),
        }

        result = lambda_handler(event, None)

        body = json.loads(result["body"])
        assert body["total_matches"] == 1
        assert body["matches"][0]["juzgado"] == "J1PF"

    def test_rejects_empty_request(self, mock_repo):
        from app.entrypoints import lambda_handler

        event = {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": "/api/upload",
            "body": json.dumps({}),
        }

        result = lambda_handler(event, None)

        assert result["statusCode"] == 400


class TestChatEndpoint:

    def test_searches_by_numero(self, mock_repo):
        from app.entrypoints import lambda_handler

        mock_repo.search_radicado.return_value = [
            Radicado(
                numero="0421", radicado="2024-0421", juzgado="J1CMIPIALES", relacion="JUAN"
            ),
        ]

        event = {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": "/api/chat",
            "body": json.dumps({"message": "0421"}),
        }

        result = lambda_handler(event, None)

        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert "0421" in body["response"]
        assert "J1CMIPIALES" in body["response"]

    def test_searches_by_name_fallback(self, mock_repo):
        from app.entrypoints import lambda_handler

        mock_repo.search_radicado.return_value = []
        mock_repo.search_by_name.return_value = [
            Radicado(
                numero="0211", radicado="2022-00211", juzgado="J1PF", relacion="RODRIGUEZ"
            ),
        ]

        event = {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": "/api/chat",
            "body": json.dumps({"message": "Rodriguez"}),
        }

        result = lambda_handler(event, None)

        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert "RODRIGUEZ" in body["response"]

    def test_no_results_shows_help(self, mock_repo):
        from app.entrypoints import lambda_handler

        mock_repo.search_radicado.return_value = []
        mock_repo.search_by_name.return_value = []

        event = {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": "/api/chat",
            "body": json.dumps({"message": "xyz123"}),
        }

        result = lambda_handler(event, None)

        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert "No se encontraron" in body["response"]

    def test_empty_message_returns_400(self, mock_repo):
        from app.entrypoints import lambda_handler

        event = {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": "/api/chat",
            "body": json.dumps({"message": ""}),
        }

        result = lambda_handler(event, None)

        assert result["statusCode"] == 400
