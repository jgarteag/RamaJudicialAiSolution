"""Bedrock adapter - implements AIService port.

Handles all communication with Amazon Bedrock for AI model invocation.
Client is cached at module level (Lambda execution context reuse).
"""

import json
import logging
from typing import Optional

import boto3

from app.domain.model import AgentConfig
from app.domain.ports import AIService

logger = logging.getLogger(__name__)


class BedrockAIService(AIService):
    """Concrete Amazon Bedrock implementation of the AIService port."""

    def __init__(self):
        self._clients: dict = {}

    def _get_client(self, region: str):
        """Get or create Bedrock client for a specific region (cached)."""
        if region not in self._clients:
            self._clients[region] = boto3.client("bedrock-runtime", region_name=region)
        return self._clients[region]

    def invoke(
        self,
        message: str,
        system_prompt: str,
        config: AgentConfig,
        conversation_history: Optional[list] = None,
    ) -> tuple[str, str]:
        """Invoke Bedrock model. Returns (response_text, model_id)."""
        client = self._get_client(config.bedrock_region)

        messages = []
        if conversation_history:
            for msg in conversation_history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": message})

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "system": system_prompt,
            "messages": messages,
        })

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
        content = response_body.get("content", [])
        if content and content[0].get("type") == "text":
            return content[0]["text"], config.model_id

        return "No pude generar una respuesta.", config.model_id
