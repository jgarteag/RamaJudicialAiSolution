"""DynamoDB adapter - implements ConfigRepository port.

Handles agent configuration retrieval from DynamoDB with TTL caching.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from app.domain.model import AgentConfig
from app.domain.ports import ConfigRepository

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300

DEFAULT_CONFIG = AgentConfig()


class DynamoDBConfigRepository(ConfigRepository):
    """Concrete DynamoDB implementation of the ConfigRepository port."""

    def __init__(self, table_name: str):
        self._table_name = table_name
        self._resource = None
        self._cache: Optional[AgentConfig] = None
        self._cache_ts: Optional[datetime] = None

    def _get_table(self):
        """Get DynamoDB table resource (cached)."""
        if self._resource is None:
            self._resource = boto3.resource("dynamodb")
        return self._resource.Table(self._table_name)

    def get_agent_config(self, agent_id: str) -> AgentConfig:
        """Retrieve agent configuration with TTL caching."""
        now = datetime.now(timezone.utc)
        if self._cache and self._cache_ts:
            if (now - self._cache_ts).total_seconds() < CACHE_TTL_SECONDS:
                return self._cache

        if not self._table_name:
            self._cache = DEFAULT_CONFIG
            self._cache_ts = now
            return self._cache

        try:
            table = self._get_table()
            response = table.get_item(Key={"agentId": agent_id})

            if "Item" in response:
                item = response["Item"]
                self._cache = AgentConfig(
                    model_id=item.get("modelId", DEFAULT_CONFIG.model_id),
                    max_tokens=int(item.get("maxTokens", DEFAULT_CONFIG.max_tokens)),
                    temperature=float(item.get("temperature", DEFAULT_CONFIG.temperature)),
                    system_prompt=item.get("systemPrompt", DEFAULT_CONFIG.system_prompt),
                    bedrock_region=item.get("bedrockRegion", DEFAULT_CONFIG.bedrock_region),
                )
            else:
                self._cache = DEFAULT_CONFIG
            self._cache_ts = now
        except ClientError as e:
            logger.warning("Failed to load config from DynamoDB", extra={"error": str(e)})
            self._cache = DEFAULT_CONFIG
            self._cache_ts = now

        return self._cache
