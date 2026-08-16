"""Tests for Bedrock adapter - Amazon Nova model support.

TDD: These tests define the expected behavior for Nova models.
Nova has a different API contract than Anthropic Claude:
- Request: schemaVersion, inferenceConfig.maxTokens, system as list, content as list of blocks
- Response: output.message.content, stopReason (camelCase)
- Tools: toolConfig.tools[].toolSpec with inputSchema.json
"""

import json
from unittest.mock import MagicMock

import pytest
from app.adapters.bedrock_adapter import BedrockAIService, _is_nova_model
from app.domain.model import AgentConfig, ToolDefinition

# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def service():
    """Bedrock service with a pre-injected mock client."""
    svc = BedrockAIService()
    mock_client = MagicMock()
    svc._clients = {"us-east-1": mock_client}
    return svc, mock_client


@pytest.fixture
def nova_config():
    return AgentConfig(
        model_id="amazon.nova-micro-v1:0",
        max_tokens=1024,
        temperature=0.7,
        system_prompt="Eres un asistente judicial.",
        bedrock_region="us-east-1",
    )


@pytest.fixture
def claude_config():
    return AgentConfig(
        model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        max_tokens=1024,
        temperature=0.7,
        system_prompt="Eres un asistente judicial.",
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
                },
                "required": ["query"],
            },
        ),
    ]


def _mock_response(mock_client, response_dict: dict):
    """Helper to set up a mock invoke_model response."""
    mock_client.invoke_model.return_value = {
        "body": MagicMock(read=MagicMock(return_value=json.dumps(response_dict).encode()))
    }


# ─── Model Detection ─────────────────────────────────────────────────────────


class TestModelDetection:
    """Unit tests for model family detection."""

    def test_nova_micro_detected(self):
        assert _is_nova_model("amazon.nova-micro-v1:0") is True

    def test_nova_lite_detected(self):
        assert _is_nova_model("amazon.nova-lite-v1:0") is True

    def test_nova_pro_detected(self):
        assert _is_nova_model("amazon.nova-pro-v1:0") is True

    def test_claude_not_detected_as_nova(self):
        assert _is_nova_model("us.anthropic.claude-haiku-4-5-20251001-v1:0") is False

    def test_claude_sonnet_not_detected_as_nova(self):
        assert _is_nova_model("anthropic.claude-3-sonnet-20240229-v1:0") is False


# ─── Nova Request Building ───────────────────────────────────────────────────


class TestNovaRequestFormat:
    """Tests that requests are built in Nova's expected format."""

    def test_invoke_sends_nova_format(self, service, nova_config):
        svc, mock_client = service
        _mock_response(mock_client, {
            "output": {"message": {"role": "assistant", "content": [{"text": "Hola!"}]}},
            "stopReason": "end_turn",
        })

        svc.invoke("hola", nova_config.system_prompt, nova_config)

        body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        # Nova format assertions
        assert body["schemaVersion"] == "messages-v1"
        assert body["system"] == [{"text": nova_config.system_prompt}]
        assert body["inferenceConfig"]["maxTokens"] == 1024
        assert body["inferenceConfig"]["temperature"] == 0.7
        # Content must be list of blocks
        assert body["messages"][0]["content"] == [{"text": "hola"}]
        # Must NOT have anthropic keys
        assert "anthropic_version" not in body
        assert "max_tokens" not in body

    def test_invoke_sends_claude_format(self, service, claude_config):
        svc, mock_client = service
        _mock_response(mock_client, {
            "content": [{"type": "text", "text": "Hola!"}],
            "stop_reason": "end_turn",
        })

        svc.invoke("hola", claude_config.system_prompt, claude_config)

        body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        # Claude format assertions
        assert body["anthropic_version"] == "bedrock-2023-05-31"
        assert body["max_tokens"] == 1024
        assert body["system"] == claude_config.system_prompt
        # Must NOT have Nova keys
        assert "schemaVersion" not in body
        assert "inferenceConfig" not in body


class TestNovaToolsFormat:
    """Tests that tools are sent in Nova's expected format."""

    def test_invoke_with_tools_uses_tool_config(self, service, nova_config, sample_tools):
        svc, mock_client = service
        _mock_response(mock_client, {
            "output": {"message": {"role": "assistant", "content": [{"text": "Hay 12 juzgados."}]}},
            "stopReason": "end_turn",
        })

        svc.invoke_with_tools(
            messages=[{"role": "user", "content": "que juzgados hay?"}],
            system_prompt=nova_config.system_prompt,
            config=nova_config,
            tools=sample_tools,
        )

        body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        # Nova wraps tools in toolConfig
        assert "toolConfig" in body
        assert "tools" not in body  # top-level "tools" is Claude format
        tools_sent = body["toolConfig"]["tools"]
        assert len(tools_sent) == 2
        # Each tool is wrapped in toolSpec
        assert "toolSpec" in tools_sent[0]
        spec = tools_sent[0]["toolSpec"]
        assert spec["name"] == "list_juzgados"
        # inputSchema must be nested under "json"
        assert "inputSchema" in spec
        assert "json" in spec["inputSchema"]
        assert spec["inputSchema"]["json"] == {"type": "object", "properties": {}}

    def test_invoke_with_tools_claude_uses_flat_tools(self, service, claude_config, sample_tools):
        svc, mock_client = service
        _mock_response(mock_client, {
            "content": [{"type": "text", "text": "respuesta"}],
            "stop_reason": "end_turn",
        })

        svc.invoke_with_tools(
            messages=[{"role": "user", "content": "hola"}],
            system_prompt=claude_config.system_prompt,
            config=claude_config,
            tools=sample_tools,
        )

        body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        assert "tools" in body
        assert "toolConfig" not in body


# ─── Nova Response Parsing ───────────────────────────────────────────────────


class TestNovaResponseParsing:
    """Tests that Nova responses are parsed correctly."""

    def test_invoke_extracts_text_from_nova_response(self, service, nova_config):
        svc, mock_client = service
        _mock_response(mock_client, {
            "output": {
                "message": {"role": "assistant", "content": [{"text": "Hola, soy tu asistente."}]}
            },
            "stopReason": "end_turn",
        })

        text, model = svc.invoke("hola", nova_config.system_prompt, nova_config)

        assert text == "Hola, soy tu asistente."
        assert model == "amazon.nova-micro-v1:0"

    def test_invoke_with_tools_parses_end_turn(self, service, nova_config, sample_tools):
        svc, mock_client = service
        _mock_response(mock_client, {
            "output": {
                "message": {"role": "assistant", "content": [{"text": "No encontré resultados."}]}
            },
            "stopReason": "end_turn",
        })

        result = svc.invoke_with_tools(
            messages=[{"role": "user", "content": "busca 2024-001"}],
            system_prompt=nova_config.system_prompt,
            config=nova_config,
            tools=sample_tools,
        )

        assert result["stop_reason"] == "end_turn"
        assert result["content"][0]["text"] == "No encontré resultados."

    def test_invoke_with_tools_parses_tool_use(self, service, nova_config, sample_tools):
        svc, mock_client = service
        _mock_response(mock_client, {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": "tool_123",
                                "name": "search_radicado",
                                "input": {"query": "2024-001"},
                            }
                        }
                    ],
                }
            },
            "stopReason": "tool_use",
        })

        result = svc.invoke_with_tools(
            messages=[{"role": "user", "content": "busca radicado 2024-001"}],
            system_prompt=nova_config.system_prompt,
            config=nova_config,
            tools=sample_tools,
        )

        assert result["stop_reason"] == "tool_use"
        # Must normalize to Claude-compatible format for the service layer
        tool_block = result["content"][0]
        assert tool_block["type"] == "tool_use"
        assert tool_block["id"] == "tool_123"
        assert tool_block["name"] == "search_radicado"
        assert tool_block["input"] == {"query": "2024-001"}

    def test_invoke_fallback_when_no_text(self, service, nova_config):
        svc, mock_client = service
        _mock_response(mock_client, {
            "output": {"message": {"role": "assistant", "content": []}},
            "stopReason": "end_turn",
        })

        text, model = svc.invoke("hola", nova_config.system_prompt, nova_config)

        assert text == "No pude generar una respuesta."


# ─── Nova Message Normalization ──────────────────────────────────────────────


class TestNovaMessageNormalization:
    """Tests that messages are normalized for Nova's expected format."""

    def test_string_content_converted_to_blocks(self, service, nova_config):
        svc, mock_client = service
        _mock_response(mock_client, {
            "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
        })

        svc.invoke_with_tools(
            messages=[
                {"role": "user", "content": "hola"},
                {"role": "assistant", "content": "soy asistente"},
                {"role": "user", "content": "busca algo"},
            ],
            system_prompt=nova_config.system_prompt,
            config=nova_config,
            tools=[],
        )

        body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        for msg in body["messages"]:
            assert isinstance(msg["content"], list), (
                f"Content should be list, got: {msg['content']}"
            )

    def test_list_content_passes_through(self, service, nova_config):
        svc, mock_client = service
        _mock_response(mock_client, {
            "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
        })

        tool_result_content = [
            {"toolResult": {"toolUseId": "t1", "content": [{"text": "data"}]}}
        ]

        svc.invoke_with_tools(
            messages=[
                {"role": "user", "content": "busca"},
                {"role": "assistant", "content": [
                    {"toolUse": {"toolUseId": "t1", "name": "search_radicado", "input": {}}}
                ]},
                {"role": "user", "content": tool_result_content},
            ],
            system_prompt=nova_config.system_prompt,
            config=nova_config,
            tools=[],
        )

        body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        # List content should pass through unchanged
        assert body["messages"][2]["content"] == tool_result_content

    def test_claude_messages_not_normalized(self, service, claude_config):
        svc, mock_client = service
        _mock_response(mock_client, {
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
        })

        svc.invoke_with_tools(
            messages=[{"role": "user", "content": "hola"}],
            system_prompt=claude_config.system_prompt,
            config=claude_config,
            tools=[],
        )

        body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        # Claude accepts string content — should NOT be converted
        assert body["messages"][0]["content"] == "hola"



# ─── Nova Tool Result Format ─────────────────────────────────────────────────


class TestNovaToolResultNormalization:
    """Tests that tool_result messages are normalized for Nova.

    The ToolUseChatService sends tool results in Claude format:
    [{"type": "tool_result", "tool_use_id": "...", "content": "..."}]

    Nova expects:
    [{"toolResult": {"toolUseId": "...", "content": [{"text": "..."}]}}]
    """

    def test_tool_result_normalized_for_nova(self, service, nova_config):
        svc, mock_client = service
        _mock_response(mock_client, {
            "output": {
                "message": {"role": "assistant", "content": [{"text": "Encontré 3 resultados."}]}
            },
            "stopReason": "end_turn",
        })

        # This is what ToolUseChatService sends after executing a tool
        claude_tool_results = [
            {"type": "tool_result", "tool_use_id": "tool_123", "content": '{"results": []}'}
        ]

        svc.invoke_with_tools(
            messages=[
                {"role": "user", "content": "busca 2024-001"},
                {"role": "assistant", "content": [
                    {
                        "type": "tool_use",
                        "id": "tool_123",
                        "name": "search_radicado",
                        "input": {"query": "2024-001"},
                    }
                ]},
                {"role": "user", "content": claude_tool_results},
            ],
            system_prompt=nova_config.system_prompt,
            config=nova_config,
            tools=[],
        )

        body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        # The tool result message should be in Nova format
        tool_result_msg = body["messages"][2]
        result_block = tool_result_msg["content"][0]
        assert "toolResult" in result_block
        assert result_block["toolResult"]["toolUseId"] == "tool_123"
        assert result_block["toolResult"]["content"] == [{"text": '{"results": []}'}]

    def test_assistant_tool_use_normalized_for_nova(self, service, nova_config):
        svc, mock_client = service
        _mock_response(mock_client, {
            "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}},
            "stopReason": "end_turn",
        })

        # Assistant message with Claude-format tool_use blocks
        svc.invoke_with_tools(
            messages=[
                {"role": "user", "content": "busca"},
                {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "t1", "name": "list_juzgados", "input": {}}
                ]},
                {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "data"}
                ]},
            ],
            system_prompt=nova_config.system_prompt,
            config=nova_config,
            tools=[],
        )

        body = json.loads(mock_client.invoke_model.call_args[1]["body"])
        # Assistant content should convert tool_use to Nova's toolUse format
        assistant_block = body["messages"][1]["content"][0]
        assert "toolUse" in assistant_block
        assert assistant_block["toolUse"]["toolUseId"] == "t1"
        assert assistant_block["toolUse"]["name"] == "list_juzgados"
