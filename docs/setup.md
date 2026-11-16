# Local developer setup

## Prerequisites
- Docker Desktop (running), Git, Node 22+, Python 3.12 (3.11 works for local tests)
- Windows: `winget install ezwinports.make`; run commands from PowerShell, or set `MSYS_NO_PATHCONV=1` in Git Bash. Do not `export` `.env` in Git Bash.

## Run the whole stack
```
python scripts/bootstrap_env.py   # writes .env with fresh secrets (never commit it)
make up                           # or: docker compose up -d --build
```
Open http://localhost:8080. Useful checks:
- http://localhost:8080/health/ready → `{"status":"ok","checks":{"database":"ok","redis":"ok"}}`
- http://localhost:8080/api/docs → interactive API docs (disabled in production)

`make logs`, `make ps`, `make down`.

## Backend without Docker
```
cd apps/backend
python -m venv .venv && .venv/Scripts/activate        # Windows (source .venv/bin/activate elsewhere)
pip install -e ".[dev]"                                # needs Python 3.12
pytest -q && ruff check . && ruff format --check . && mypy app
```

## Web without Docker
```
cd apps/web
npm ci
npm run dev          # http://localhost:3000 (API calls need the gateway at :8080)
npm run lint && npm run typecheck && npm test && npm run build
```

## After changing an API schema
`make types` regenerates `packages/api-types/openapi.json` and `index.ts`. CI fails if they are stale.

Without make:
```
cd apps/backend && python -m scripts.export_openapi > ../../packages/api-types/openapi.json
cd ../../packages/api-types && npm ci && npm run generate
```
