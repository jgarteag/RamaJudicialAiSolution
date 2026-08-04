"""Tests for Bedrock adapter with tool use support."""

import json
from unittest.mock import MagicMock, patch

import pytest
from app.adapters.bedrock_adapter import BedrockAIService
from app.domain.model import AgentConfig, ToolDefinition


@pytest.fixture
def bedrock_service():
    return BedrockAIService()


@pytest.fixture
def config():
    return AgentConfig(
        model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        max_tokens=1024,
        temperature=0.7,
        system_prompt="Test prompt",
        bedrock_region="us-east-1",
    )


@pytest.fixture
def sample_tools():
    return [
        ToolDefinition(
            name="list_juzgados",
            description="Lista todos los juzgados disponibles",
            input_schema={"type": "object", "properties": {}},
        ),
        ToolDefinition(
            name="search_radicado",
            description="Busca un radicado por número",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Número a buscar"},
                    "juzgado": {"type": "string", "description": "Juzgado (opcional)"},
                },
                "required": ["query"],
            },
        ),
    ]


class TestToolDefinitionSerialization:
    """Test that ToolDefinition serializes correctly for Bedrock API."""

    def test_tool_definition_to_bedrock_format(self, sample_tools):
        tool = sample_tools[0]
        bedrock_format = tool.to_bedrock_format()
        assert bedrock_format["name"] == "list_juzgados"
        assert bedrock_format["description"] == "Lista todos los juzgados disponibles"
        assert "input_schema" in bedrock_format

    def test_tool_definition_with_required_params(self, sample_tools):
        tool = sample_tools[1]
        bedrock_format = tool.to_bedrock_format()
        schema = bedrock_format["input_schema"]
        assert "query" in schema["properties"]
        assert "required" in schema


class TestBedrockInvokeWithTools:
    """Test Bedrock adapter invoke_with_tools method."""

    @patch("boto3.client")
    def test_invoke_with_tools_sends_correct_body(
        self, mock_boto, bedrock_service, config, sample_tools
    ):
        mock_client = MagicMock()
        mock_boto.return_value = mock_client

        mock_response_body = json.dumps({
            "content": [{"type": "text", "text": "response"}],
            "stop_reason": "end_turn",
            "model": config.model_id,
        }).encode()

        mock_client.invoke_model.return_value = {
            "body": MagicMock(read=MagicMock(return_value=mock_response_body))
        }

        bedrock_service._clients = {"us-east-1": mock_client}

        bedrock_service.invoke_with_tools(
            messages=[{"role": "user", "content": "hola"}],
            system_prompt="Test",
            config=config,
            tools=sample_tools,
        )

        # Verify the body sent to Bedrock includes tools
        call_args = mock_client.invoke_model.call_args
        body = json.loads(call_args[1]["body"])
        assert "tools" in body
        assert len(body["tools"]) == 2
        assert body["tools"][0]["name"] == "list_juzgados"

    @patch("boto3.client")
    def test_invoke_with_tools_returns_tool_use_response(
        self, mock_boto, bedrock_service, config, sample_tools
    ):
        mock_client = MagicMock()
        mock_boto.return_value = mock_client

        mock_response_body = json.dumps({
            "content": [
                {"type": "tool_use", "id": "tool_abc", "name": "list_juzgados", "input": {}}
            ],
            "stop_reason": "tool_use",
            "model": config.model_id,
        }).encode()

        mock_client.invoke_model.return_value = {
            "body": MagicMock(read=MagicMock(return_value=mock_response_body))
        }

        bedrock_service._clients = {"us-east-1": mock_client}

        result = bedrock_service.invoke_with_tools(
            messages=[{"role": "user", "content": "que juzgados hay?"}],
            system_prompt="Test",
            config=config,
            tools=sample_tools,
        )

        assert result["stop_reason"] == "tool_use"
        assert result["content"][0]["type"] == "tool_use"
        assert result["content"][0]["name"] == "list_juzgados"

    @patch("boto3.client")
    def test_invoke_with_tools_handles_text_response(
        self, mock_boto, bedrock_service, config, sample_tools
    ):
        mock_client = MagicMock()

        mock_response_body = json.dumps({
            "content": [{"type": "text", "text": "Hola, soy tu asistente."}],
            "stop_reason": "end_turn",
            "model": config.model_id,
        }).encode()

        mock_client.invoke_model.return_value = {
            "body": MagicMock(read=MagicMock(return_value=mock_response_body))
        }

        bedrock_service._clients = {"us-east-1": mock_client}

        result = bedrock_service.invoke_with_tools(
            messages=[{"role": "user", "content": "hola"}],
            system_prompt="Test",
            config=config,
            tools=sample_tools,
        )

        assert result["stop_reason"] == "end_turn"
        assert result["content"][0]["text"] == "Hola, soy tu asistente."
