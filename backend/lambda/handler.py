"""Lambda handler entry point.

This file exists at the root of the Lambda package as the handler reference
(handler.lambda_handler) configured in Terraform. It simply re-exports the
actual handler from the hexagonal architecture entrypoint.

Structure (AWS Prescriptive Guidance - Hexagonal Architecture):
    app/
    ├── domain/           # Business logic (no external deps)
    │   ├── model/        # Entities
    │   ├── ports/        # Abstract interfaces (contracts)
    │   └── services/     # Use cases / orchestration
    ├── adapters/         # Secondary adapters (implement ports)
    │   ├── mongodb_adapter.py
    │   ├── bedrock_adapter.py
    │   ├── dynamodb_adapter.py
    │   └── secrets_adapter.py
    └── entrypoints/      # Primary adapter (this handler)
"""

from app.entrypoints import lambda_handler  # noqa: F401
