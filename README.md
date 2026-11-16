# RedStarVibe

Business pages, bookings, orders, a local social feed, chat and AI in one platform. Small businesses and skilled workers get a page at `redstarvibe.com/{username}` and run their daily work from it.

**Status:** Phase 0 complete — see [docs/STATUS.md](docs/STATUS.md).

## Quick start
```
python scripts/bootstrap_env.py
make up            # http://localhost:8080
```
Full instructions: [docs/setup.md](docs/setup.md).

## Repository
| Path | What |
|---|---|
| `apps/backend` | Python 3.12 FastAPI modular monolith (api, worker, beat, migrate processes) |
| `apps/web` | Next.js 16 / React 19 responsive PWA |
| `packages/api-types` | TypeScript types generated from OpenAPI |
| `infra` | Docker images, nginx gateway, scripts, monitoring |
| `docs` | ADRs, runbooks, audit, status |

## Key documents
- `RedStarVibe_Production_Blueprint_v4.docx` — product and architecture source of truth
- `RedStarVibe_Development_Execution_Plan.md` — phase-by-phase plan
- `CLAUDE.md` — engineering rules for contributors and Claude Code
- `docs/adr/` — architecture decisions
