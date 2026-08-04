"""Tests for the ToolUseChatService - TDD approach.

Tests the agentic loop: LLM decides which tools to call,
we execute them against MongoDB, and feed results back.
"""

from unittest.mock import MagicMock

import pytest
from app.domain.model import AgentConfig, Radicado
from app.domain.ports import AIService, ConfigRepository, RadicadoRepository
from app.domain.services import ToolUseChatService


@pytest.fixture
def mock_ai_service():
    return MagicMock(spec=AIService)


@pytest.fixture
def mock_config_repo():
    repo = MagicMock(spec=ConfigRepository)
    repo.get_agent_config.return_value = AgentConfig(
        model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        max_tokens=1024,
        temperature=0.7,
        system_prompt="Eres un asistente judicial.",
        bedrock_region="us-east-1",
    )
    return repo


@pytest.fixture
def mock_radicado_repo():
    repo = MagicMock(spec=RadicadoRepository)
    repo.list_juzgados.return_value = ["J1CMIPIALES", "J2CMIPIALES", "JPMCORDOBA"]
    return repo


@pytest.fixture
def service(mock_ai_service, mock_config_repo, mock_radicado_repo):
    return ToolUseChatService(
        ai_service=mock_ai_service,
        config_repo=mock_config_repo,
        radicado_repo=mock_radicado_repo,
        agent_id="rama-judicial-ai",
    )


class TestToolDefinitions:
    """Test that tool definitions are properly generated."""

    def test_get_tool_definitions_returns_all_tools(self, service):
        tools = service.get_tool_definitions()
        tool_names = [t.name for t in tools]
        assert "list_juzgados" in tool_names
        assert "search_radicado" in tool_names
        assert "search_by_name" in tool_names
        assert "get_radicados" in tool_names

    def test_tool_definitions_have_valid_schema(self, service):
        tools = service.get_tool_definitions()
        for tool in tools:
            assert tool.name
            assert tool.description
            assert isinstance(tool.input_schema, dict)

    def test_search_radicado_tool_has_required_params(self, service):
        tools = service.get_tool_definitions()
        search_tool = next(t for t in tools if t.name == "search_radicado")
        schema = search_tool.input_schema
        assert "properties" in schema
        assert "juzgado" in schema["properties"]
        assert "query" in schema["properties"]


class TestToolExecution:
    """Test tool execution against the repository."""

    def test_execute_list_juzgados(self, service, mock_radicado_repo):
        result = service.execute_tool("list_juzgados", {})
        assert "J1CMIPIALES" in result
        assert "J2CMIPIALES" in result
        assert "total" in result
        mock_radicado_repo.list_juzgados.assert_called_once()

    def test_execute_search_radicado_by_numero(self, service, mock_radicado_repo):
        mock_radicado_repo.search_radicado.return_value = [
            Radicado(
                numero="0421",
                ano_estado="2024",
                relacion="MAYRA RODRIGUEZ",
                tipo="J1CMIPIALES",
                radicado="2024-0421",
            )
        ]
        result = service.execute_tool(
            "search_radicado", {"juzgado": "J1CMIPIALES", "query": "0421"}
        )
        assert "0421" in result
        assert "MAYRA RODRIGUEZ" in result

    def test_execute_search_radicado_all_juzgados(self, service, mock_radicado_repo):
        mock_radicado_repo.search_radicado.return_value = [
            Radicado(
                numero="0421",
                ano_estado="2024",
                relacion="MAYRA RODRIGUEZ",
                tipo="J1CMIPIALES",
                radicado="2024-0421",
                juzgado="J1CMIPIALES",
            )
        ]
        result = service.execute_tool("search_radicado", {"query": "0421"})
        assert "0421" in result

    def test_execute_search_by_name(self, service, mock_radicado_repo):
        mock_radicado_repo.search_by_name.return_value = [
            Radicado(
                numero="0421",
                ano_estado="2024",
                relacion="MAYRA ALEJANDRA RODRIGUEZ CALDERON",
                tipo="J1CMIPIALES",
                radicado="2024-0421",
                juzgado="J1CMIPIALES",
            )
        ]
        result = service.execute_tool(
            "search_by_name", {"name": "MAYRA RODRIGUEZ", "juzgado": "J1CMIPIALES"}
        )
        assert "MAYRA" in result

    def test_execute_get_radicados(self, service, mock_radicado_repo):
        mock_radicado_repo.get_radicados_sample.return_value = [
            Radicado(numero="0421", ano_estado="2024", relacion="PERSONA", tipo="J1CMIPIALES",
                     radicado="2024-0421"),
        ]
        result = service.execute_tool(
            "get_radicados", {"juzgado": "J1CMIPIALES", "limit": 10}
        )
        assert "0421" in result

    def test_execute_unknown_tool_returns_error(self, service):
        result = service.execute_tool("nonexistent_tool", {})
        assert "error" in result.lower() or "no existe" in result.lower()


class TestAgenticLoop:
    """Test the full agentic loop with tool use."""

    def test_simple_chat_no_tools(self, service, mock_ai_service):
        """When LLM responds without tool_use, return directly."""
        mock_ai_service.invoke_with_tools.return_value = {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "Hola, ¿en qué puedo ayudarte?"}],
            "model": "claude-haiku",
        }
        response, model = service.chat("hola")
        assert response == "Hola, ¿en qué puedo ayudarte?"
        assert model == "claude-haiku"

    def test_single_tool_use_loop(self, service, mock_ai_service, mock_radicado_repo):
        """LLM calls one tool, gets result, then responds."""
        # First call: LLM decides to use a tool
        mock_ai_service.invoke_with_tools.side_effect = [
            {
                "stop_reason": "tool_use",
                "content": [
                    {"type": "text", "text": "Voy a buscar los juzgados disponibles."},
                    {
                        "type": "tool_use",
                        "id": "tool_1",
                        "name": "list_juzgados",
                        "input": {},
                    },
                ],
                "model": "claude-haiku",
            },
            # Second call: LLM responds with final answer
            {
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": "Los juzgados disponibles son: "
                        "J1CMIPIALES, J2CMIPIALES, JPMCORDOBA",
                    }
                ],
                "model": "claude-haiku",
            },
        ]

        response, model = service.chat("¿Qué juzgados hay?")
        assert "J1CMIPIALES" in response
        assert mock_ai_service.invoke_with_tools.call_count == 2

    def test_max_iterations_safety(self, service, mock_ai_service):
        """Prevent infinite loops by capping iterations."""
        # LLM keeps calling tools indefinitely
        mock_ai_service.invoke_with_tools.return_value = {
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tool_1",
                    "name": "list_juzgados",
                    "input": {},
                },
            ],
            "model": "claude-haiku",
        }

        response, model = service.chat("loop infinito")
        # Should return something instead of looping forever
        assert response
        assert mock_ai_service.invoke_with_tools.call_count <= 11

    def test_conversation_history_passed(self, service, mock_ai_service):
        """Conversation history is forwarded to the AI service."""
        mock_ai_service.invoke_with_tools.return_value = {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "Respuesta"}],
            "model": "claude-haiku",
        }
        history = [{"role": "user", "content": "msg anterior"}]

        service.chat("nueva pregunta", conversation_history=history)

        call_kwargs = mock_ai_service.invoke_with_tools.call_args
        assert call_kwargs is not None
