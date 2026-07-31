.PHONY: lint lint-fix fmt-check

lint:
	uvx ruff check backend/lambda
	terraform fmt -check -recursive infrastructure

lint-fix:
	uvx ruff check --fix backend/lambda

fmt-check:
	terraform fmt -check -recursive infrastructure
