"""DynamoDB adapter - implements ConfigRepository port.

Handles agent configuration retrieval from DynamoDB with TTL caching.
All configuration MUST exist in DynamoDB; no defaults are assumed.
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
        """Retrieve agent configuration from DynamoDB (required).

        Raises ValueError if the table is not configured or the item is missing.
        """
        now = datetime.now(timezone.utc)
        if self._cache and self._cache_ts:
            if (now - self._cache_ts).total_seconds() < CACHE_TTL_SECONDS:
                return self._cache

        if not self._table_name:
            raise ValueError(
                "DynamoDB table name is not configured. "
                "Agent configuration must be stored in DynamoDB."
            )

        try:
            table = self._get_table()
            response = table.get_item(Key={"agentId": agent_id})

            if "Item" not in response:
                raise ValueError(
                    f"Agent config not found in DynamoDB for agentId='{agent_id}'. "
                    "All configuration must exist in the table."
                )

            item = response["Item"]
            self._cache = AgentConfig(
                model_id=item["modelId"],
                max_tokens=int(item["maxTokens"]),
                temperature=float(item["temperature"]),
                system_prompt=item["systemPrompt"],
                bedrock_region=item["bedrockRegion"],
            )
            self._cache_ts = now
        except ClientError as e:
            logger.error("Failed to load config from DynamoDB", extra={"error": str(e)})
            raise ValueError(
                f"Could not retrieve agent config from DynamoDB: {e}"
            ) from e

        return self._cache
