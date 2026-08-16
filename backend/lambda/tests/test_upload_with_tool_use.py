"""Tests for the upload endpoint using ToolUseChatService.

The upload flow should:
1. Accept multiple files (no limit)
2. Extract text from each file
3. Pass all extracted text to ToolUseChatService
4. Let the LLM decide how to search (tool-use pattern)
5. Return the LLM response + metadata about processed files
"""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest
from app.domain.model import AgentConfig
from app.domain.ports import AIService, ConfigRepository, RadicadoRepository
from app.domain.services import ToolUseChatService


@pytest.fixture
def mock_ai_service():
    svc = MagicMock(spec=AIService)
    svc.invoke_with_tools.return_value = {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "Encontré 1 coincidencia en J2PF."}],
        "model": "claude-haiku",
    }
    return svc


@pytest.fixture
def mock_config_repo():
    repo = MagicMock(spec=ConfigRepository)
    repo.get_agent_config.return_value = AgentConfig(
        model_id="claude-haiku",
        max_tokens=4096,
        temperature=0.7,
        system_prompt="Test prompt",
        bedrock_region="us-east-1",
    )
    return repo


@pytest.fixture
def mock_radicado_repo():
    repo = MagicMock(spec=RadicadoRepository)
    repo.list_juzgados.return_value = ["J1CMIPIALES", "J2PF", "JPMPUPIALES"]
    return repo


@pytest.fixture
def service(mock_ai_service, mock_config_repo, mock_radicado_repo):
    return ToolUseChatService(
        ai_service=mock_ai_service,
        config_repo=mock_config_repo,
        radicado_repo=mock_radicado_repo,
        agent_id="rama-judicial-ai",
    )


class TestUploadTextExtraction:
    """Test that text is correctly extracted and passed to the chat service."""

    def test_single_file_text_passed_to_chat(self, service, mock_ai_service):
        """When upload sends text, chat receives it as a message."""
        file_text = "Radicado 2024-00065 del Juzgado Segundo Promiscuo de Familia"

        response, model = service.chat(
            f"Busca coincidencias en la base de datos:\n--- Archivo: test.pdf ---\n{file_text}"
        )

        assert response == "Encontré 1 coincidencia en J2PF."
        assert model == "claude-haiku"
        mock_ai_service.invoke_with_tools.assert_called_once()

    def test_multiple_files_concatenated(self, service, mock_ai_service):
        """Multiple file texts are concatenated in the message."""
        texts = [
            "--- Archivo: doc1.pdf ---\nRadicado 2024-0421",
            "--- Archivo: doc2.pdf ---\nRadicado 2025-00014",
        ]
        combined = "\n\n".join(texts)
        message = f"El usuario subió 2 documento(s). Busca coincidencias.\n\n{combined}"

        response, _ = service.chat(message)

        call_args = mock_ai_service.invoke_with_tools.call_args
        sent_messages = call_args[1]["messages"]
        user_msg = sent_messages[-1]["content"]
        assert "doc1.pdf" in user_msg
        assert "doc2.pdf" in user_msg
        assert "2024-0421" in user_msg
        assert "2025-00014" in user_msg

    def test_juzgado_hint_included_in_message(self, service, mock_ai_service):
        """When user selects a juzgado, it's included in the message."""
        message = (
            "El usuario subió 1 documento(s). "
            "Busca coincidencias de radicados en el juzgado J2PF.\n\n"
            "--- Archivo: test.pdf ---\nRadicado 2024-00065"
        )

        service.chat(message)

        call_args = mock_ai_service.invoke_with_tools.call_args
        sent_messages = call_args[1]["messages"]
        user_msg = sent_messages[-1]["content"]
        assert "J2PF" in user_msg


class TestUploadEndpoint:
    """Test the upload Lambda handler logic."""

    def test_upload_extracts_text_and_calls_tool_use(self):
        """Full upload flow: decode base64 → extract text → ToolUseChatService."""
        from app.entrypoints import lambda_handler

        # Create a simple text file as base64
        text_content = "Radicado 2024-00065\nRadicado 2025-00014"
        file_b64 = base64.b64encode(text_content.encode()).decode()

        event = {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": "/api/upload",
            "body": json.dumps({
                "files": [{"file": file_b64, "filename": "estados.txt"}],
                "juzgado": "",
            }),
        }

        with patch("app.entrypoints._get_ai_service") as mock_ai, \
             patch("app.entrypoints._get_config_repo") as mock_config, \
             patch("app.entrypoints._get_radicado_repo") as mock_repo:

            mock_ai_svc = MagicMock()
            mock_ai_svc.invoke_with_tools.return_value = {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Encontré coincidencias."}],
                "model": "claude-haiku",
            }
            mock_ai.return_value = mock_ai_svc

            mock_config_svc = MagicMock()
            mock_config_svc.get_agent_config.return_value = AgentConfig(
                model_id="test-model",
                max_tokens=1024,
                temperature=0.7,
                system_prompt="Test",
                bedrock_region="us-east-1",
            )
            mock_config.return_value = mock_config_svc

            mock_repo_svc = MagicMock()
            mock_repo_svc.list_juzgados.return_value = ["J2PF"]
            mock_repo.return_value = mock_repo_svc

            result = lambda_handler(event, None)

        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert "response" in body
        assert body["response"] == "Encontré coincidencias."
        assert "estados.txt" in body["files_processed"]

    def test_upload_skips_unsupported_formats(self):
        """Unsupported file extensions are skipped gracefully."""
        from app.entrypoints import lambda_handler

        file_b64 = base64.b64encode(b"data").decode()

        event = {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": "/api/upload",
            "body": json.dumps({
                "files": [{"file": file_b64, "filename": "image.png"}],
            }),
        }

        result = lambda_handler(event, None)
        assert result["statusCode"] == 400

    def test_upload_handles_empty_file(self):
        """Empty file field is skipped."""
        from app.entrypoints import lambda_handler

        event = {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": "/api/upload",
            "body": json.dumps({
                "files": [{"file": "", "filename": "empty.txt"}],
            }),
        }

        result = lambda_handler(event, None)
        assert result["statusCode"] == 400

    def test_upload_multiple_files_all_processed(self):
        """Multiple valid files are all processed."""
        from app.entrypoints import lambda_handler

        file1 = base64.b64encode(b"Radicado 2024-0421").decode()
        file2 = base64.b64encode(b"Radicado 2025-00014").decode()

        event = {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": "/api/upload",
            "body": json.dumps({
                "files": [
                    {"file": file1, "filename": "doc1.txt"},
                    {"file": file2, "filename": "doc2.txt"},
                ],
            }),
        }

        with patch("app.entrypoints._get_ai_service") as mock_ai, \
             patch("app.entrypoints._get_config_repo") as mock_config, \
             patch("app.entrypoints._get_radicado_repo") as mock_repo:

            mock_ai_svc = MagicMock()
            mock_ai_svc.invoke_with_tools.return_value = {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Resultados."}],
                "model": "claude-haiku",
            }
            mock_ai.return_value = mock_ai_svc

            mock_config_svc = MagicMock()
            mock_config_svc.get_agent_config.return_value = AgentConfig(
                model_id="test-model",
                max_tokens=1024,
                temperature=0.7,
                system_prompt="Test",
                bedrock_region="us-east-1",
            )
            mock_config.return_value = mock_config_svc

            mock_repo_svc = MagicMock()
            mock_repo_svc.list_juzgados.return_value = ["J2PF"]
            mock_repo.return_value = mock_repo_svc

            result = lambda_handler(event, None)

        body = json.loads(result["body"])
        assert result["statusCode"] == 200
        assert "doc1.txt" in body["files_processed"]
        assert "doc2.txt" in body["files_processed"]

    def test_upload_with_juzgado_filter(self):
        """When juzgado is provided, it's included in the message to the LLM."""
        from app.entrypoints import lambda_handler

        file_b64 = base64.b64encode(b"Radicado 2024-00065").decode()

        event = {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": "/api/upload",
            "body": json.dumps({
                "files": [{"file": file_b64, "filename": "test.txt"}],
                "juzgado": "J2PF",
            }),
        }

        with patch("app.entrypoints._get_ai_service") as mock_ai, \
             patch("app.entrypoints._get_config_repo") as mock_config, \
             patch("app.entrypoints._get_radicado_repo") as mock_repo:

            mock_ai_svc = MagicMock()
            mock_ai_svc.invoke_with_tools.return_value = {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "OK"}],
                "model": "claude-haiku",
            }
            mock_ai.return_value = mock_ai_svc

            mock_config_svc = MagicMock()
            mock_config_svc.get_agent_config.return_value = AgentConfig(
                model_id="test-model",
                max_tokens=1024,
                temperature=0.7,
                system_prompt="Test",
                bedrock_region="us-east-1",
            )
            mock_config.return_value = mock_config_svc

            mock_repo_svc = MagicMock()
            mock_repo_svc.list_juzgados.return_value = ["J2PF"]
            mock_repo.return_value = mock_repo_svc

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        # Verify that J2PF was in the message sent to the LLM
        call_args = mock_ai_svc.invoke_with_tools.call_args
        messages = call_args[1]["messages"]
        user_msg = messages[-1]["content"]
        assert "J2PF" in user_msg
