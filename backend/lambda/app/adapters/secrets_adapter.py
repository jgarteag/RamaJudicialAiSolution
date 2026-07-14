"""Secrets Manager adapter - implements SecretProvider port.

Handles retrieving secrets from AWS Secrets Manager with caching.
"""

import logging
from typing import Optional

import boto3

from app.domain.ports import SecretProvider

logger = logging.getLogger(__name__)


class SecretsManagerProvider(SecretProvider):
    """Concrete AWS Secrets Manager implementation of the SecretProvider port."""

    def __init__(self):
        self._client = None
        self._cache: dict[str, str] = {}

    def _get_client(self):
        """Get Secrets Manager client (cached)."""
        if self._client is None:
            self._client = boto3.client("secretsmanager")
        return self._client

    def get_secret(self, secret_name: str) -> str:
        """Retrieve and cache a secret value."""
        if secret_name in self._cache:
            return self._cache[secret_name]

        if not secret_name:
            raise ValueError("Secret name not configured")

        client = self._get_client()
        response = client.get_secret_value(SecretId=secret_name)
        value = response["SecretString"]
        self._cache[secret_name] = value
        logger.info("Secret loaded from Secrets Manager (cached)", extra={"secret": secret_name})
        return value
