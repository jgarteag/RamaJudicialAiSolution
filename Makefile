.PHONY: lint lint-fix fmt-check test

lint:
	uvx ruff check backend/lambda

lint-fix:
	uvx ruff check --fix backend/lambda

fmt-check:
	terraform fmt -check -recursive infrastructure

test:
	uv run pytest backend/lambda/tests -v
