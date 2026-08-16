import json
import logging
from typing import Optional

import boto3

from app.domain.model import AgentConfig, ToolDefinition
from app.domain.ports import AIService

logger = logging.getLogger(__name__)


def _is_nova_model(model_id: str) -> bool:
    return "nova" in model_id.lower()


class BedrockAIService(AIService):

    def __init__(self):
        self._clients: dict = {}

    def _get_client(self, region: str):
        if region not in self._clients:
            self._clients[region] = boto3.client("bedrock-runtime", region_name=region)
        return self._clients[region]

    def _build_nova_body(
        self,
        config: AgentConfig,
        messages: list[dict],
        system_prompt: str,
        tools: Optional[list[dict]] = None,
    ) -> dict:
        body = {
            "schemaVersion": "messages-v1",
            "messages": messages,
            "system": [{"text": system_prompt}],
            "inferenceConfig": {
                "maxTokens": config.max_tokens,
                "temperature": config.temperature,
            },
        }
        if tools:
            nova_tools = []
            for t in tools:
                schema = t.get("input_schema") or t.get("inputSchema", {})
                nova_tools.append({"toolSpec": {
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": {"json": schema},
                }})
            body["toolConfig"] = {"tools": nova_tools}
        return body

    def _build_claude_body(
        self,
        config: AgentConfig,
        messages: list[dict],
        system_prompt: str,
        tools: Optional[list[dict]] = None,
    ) -> dict:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "system": system_prompt,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools
        return body

    def _build_body(
        self,
        config: AgentConfig,
        messages: list[dict],
        system_prompt: str,
        tools: Optional[list[dict]] = None,
    ) -> str:
        if _is_nova_model(config.model_id):
            body = self._build_nova_body(config, messages, system_prompt, tools)
        else:
            body = self._build_claude_body(config, messages, system_prompt, tools)
        return json.dumps(body)

    def _parse_nova_response(self, response_body: dict, model_id: str) -> dict:
        output = response_body.get("output", {})
        message = output.get("message", {})
        raw_content = message.get("content", [])
        stop_reason = response_body.get("stopReason", "end_turn")

        content = []
        for block in raw_content:
            if "text" in block:
                content.append({"type": "text", "text": block["text"]})
            elif "toolUse" in block:
                tu = block["toolUse"]
                content.append({
                    "type": "tool_use",
                    "id": tu["toolUseId"],
                    "name": tu["name"],
                    "input": tu.get("input", {}),
                })
            else:
                content.append(block)

        return {"stop_reason": stop_reason, "content": content, "model": model_id}

    def _parse_claude_response(self, response_body: dict, model_id: str) -> dict:
        return {
            "stop_reason": response_body.get("stop_reason", "end_turn"),
            "content": response_body.get("content", []),
            "model": model_id,
        }

    def _parse_response(self, response_body: dict, model_id: str) -> dict:
        if _is_nova_model(model_id):
            return self._parse_nova_response(response_body, model_id)
        return self._parse_claude_response(response_body, model_id)

    def _normalize_messages(self, messages: list[dict], model_id: str) -> list[dict]:
        if not _is_nova_model(model_id):
            return messages

        normalized = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                normalized.append({"role": msg["role"], "content": [{"text": content}]})
            elif isinstance(content, list):
                nova_blocks = [self._to_nova_block(block) for block in content]
                normalized.append({"role": msg["role"], "content": nova_blocks})
            else:
                normalized.append(msg)
        return normalized

    @staticmethod
    def _to_nova_block(block: dict) -> dict:
        block_type = block.get("type")

        if block_type == "tool_use":
            return {
                "toolUse": {
                    "toolUseId": block["id"],
                    "name": block["name"],
                    "input": block.get("input", {}),
                }
            }

        if block_type == "tool_result":
            content_value = block.get("content", "")
            if isinstance(content_value, str):
                result_content = [{"text": content_value}]
            elif isinstance(content_value, list):
                result_content = content_value
            else:
                result_content = [{"text": str(content_value)}]
            return {
                "toolResult": {
                    "toolUseId": block["tool_use_id"],
                    "content": result_content,
                }
            }

        if block_type == "text":
            return {"text": block["text"]}

        return block

    def invoke(
        self,
        message: str,
        system_prompt: str,
        config: AgentConfig,
        conversation_history: Optional[list] = None,
    ) -> tuple[str, str]:
        client = self._get_client(config.bedrock_region)

        messages = []
        if conversation_history:
            for msg in conversation_history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": message})

        normalized = self._normalize_messages(messages, config.model_id)
        body = self._build_body(config, normalized, system_prompt)

        logger.info(
            "Invoking Bedrock",
            extra={"model": config.model_id, "messages_count": len(messages)},
        )

        response = client.invoke_model(
            modelId=config.model_id,
            contentType="application/json",
            accept="application/json",
            body=body,
        )

        response_body = json.loads(response["body"].read())
        parsed = self._parse_response(response_body, config.model_id)

        content = parsed.get("content", [])
        if content and content[0].get("type") == "text":
            return content[0]["text"], config.model_id

        return "No pude generar una respuesta.", config.model_id

    def invoke_with_tools(
        self,
        messages: list[dict],
        system_prompt: str,
        config: AgentConfig,
        tools: list[ToolDefinition],
    ) -> dict:
        client = self._get_client(config.bedrock_region)

        bedrock_tools = [tool.to_bedrock_format() for tool in tools]

        normalized = self._normalize_messages(messages, config.model_id)
        body = self._build_body(config, normalized, system_prompt, tools=bedrock_tools)

        logger.info(
            "Invoking Bedrock with tools",
            extra={
                "model": config.model_id,
                "messages_count": len(messages),
                "tools_count": len(bedrock_tools),
            },
        )

        response = client.invoke_model(
            modelId=config.model_id,
            contentType="application/json",
            accept="application/json",
            body=body,
        )

        response_body = json.loads(response["body"].read())
        return self._parse_response(response_body, config.model_id)
