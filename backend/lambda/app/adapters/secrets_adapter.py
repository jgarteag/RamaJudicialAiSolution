import boto3

from app.domain.ports import SecretProvider


class SecretsManagerProvider(SecretProvider):

    def __init__(self):
        self._client = None
        self._cache: dict[str, str] = {}

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client("secretsmanager")
        return self._client

    def get_secret(self, secret_name: str) -> str:
        if secret_name in self._cache:
            return self._cache[secret_name]

        if not secret_name:
            raise ValueError("Secret name not configured")

        client = self._get_client()
        response = client.get_secret_value(SecretId=secret_name)
        value = response["SecretString"]
        self._cache[secret_name] = value
        return value
