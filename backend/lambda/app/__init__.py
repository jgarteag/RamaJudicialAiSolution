"""Rama Judicial AI - Lambda application.

Hexagonal architecture following AWS Prescriptive Guidance:
- domain/    → Business logic + ports (no external dependencies)
- adapters/  → Secondary adapters (implement ports for MongoDB, Bedrock, etc.)
- entrypoints/ → Primary adapter (Lambda handler, parses events, wires DI)
"""
