# Windows: install make with `winget install ezwinports.make`, run from PowerShell
# (or set MSYS_NO_PATHCONV=1 in Git Bash). Do not `export` .env in Git Bash.

COMPOSE ?= docker compose
BACKEND = $(COMPOSE) run --rm --no-deps api

.PHONY: env up down logs ps migrate seed test lint fmt test-web lint-web e2e types load build

env:            ## first run: write .env with fresh secrets
	python scripts/bootstrap_env.py

up: env         ## build + start + migrate -> http://localhost:8080
	$(COMPOSE) up -d --build
	@echo "RedStarVibe is starting on http://localhost:8080"

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

migrate:
	$(COMPOSE) run --rm migrate

seed:           ## demo data (added with the first domain modules)
	$(BACKEND) python -m scripts.seed

test:           ## backend tests (inside the backend image)
	$(BACKEND) pytest -q

lint:
	$(BACKEND) sh -c "ruff check . && ruff format --check . && mypy app"

fmt:
	$(BACKEND) sh -c "ruff check --fix . && ruff format ."

test-web:
	cd apps/web && npm test

lint-web:
	cd apps/web && npm run lint && npm run typecheck

e2e:            ## Playwright (added with the first user journeys)
	cd apps/web && npx playwright test

types:          ## regenerate OpenAPI + @rsv/api-types; CI fails if stale
	$(BACKEND) python -m scripts.export_openapi > packages/api-types/openapi.json
	cd packages/api-types && npm run generate

load:           ## k6 baseline (added in Phase 1)
	k6 run infra/scripts/load/baseline.js
