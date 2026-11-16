# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

**RedStarVibe** (redstarvibe.com) is a social and business platform for India. Small businesses and skilled workers (electricians, welders, drivers, shops, event companies) get a public page at `redstarvibe.com/{username}`. From that page they take bookings, orders and event-package enquiries. A social feed, stories, chat, shareable cards and AI tools bring people back.

Go-to-market: launch in one city with 2–3 trades, and onboard 20–30 real businesses in person. Start each phase only after real people use the previous one.

## Repository state (read first)

This repo currently holds **only planning documents. There is no application code yet.**

| File | Role |
|---|---|
| `RedStarVibe_Production_Blueprint_v4.docx` | **Source of truth** (v4.0, 3 Nov 2026). Replaces all earlier docs. |
| `RedStarVibe_Development_Execution_Plan.md` | Phase-by-phase execution guide, Definition of Done, checklists. Based on Blueprint v4. |
| `RedStarVibe_Technical_Architecture.docx` | v1.0 background. **Several of its choices are superseded** (see "Decisions" below). |
| `RedStarVibe_Master_Implementation_Plan.docx` | Early summary. Its phase order and some stack choices are superseded. |

The Blueprint describes some features as "already built" (auth, posts/media, feed, search, RAG, MCP, business page, admin). Those claims came from an earlier codebase. **Never treat a feature as done until you have verified its code and tests in this repo.**

When docs conflict, use the Blueprint v4. When code and docs differ, inspect the code, confirm whether the difference is intentional, and record the decision as an ADR in `docs/adr/`. Never run a risky migration just to make code match a document.

## Branches

- `main`, `dev`, `staging` and `production` all exist on `origin` (github.com/aarvitechai/RedStarVibeV4).
- Day-to-day work happens on `dev` or on short-lived feature branches off `dev`.
- The Blueprint describes trunk-based development where "merge to main deploys staging". The `dev` → `staging` → `production` branch flow differs from that. Write an ADR for the chosen flow before you set up CI/CD deploy workflows.
- Use Conventional Commits, small PRs, and a PR review for every production change. Never commit secrets.

## Stack (final decisions from Blueprint v4)

- **Frontend:** Next.js 16, React 19, TypeScript strict. TanStack Query for server state; Zustand only for shared client state; React Hook Form + Zod.
- **UI:** hand-written primitives with CSS-variable design tokens (`apps/web/src/styles/tokens.css`). **No shadcn/ui or Tailwind component kit** without an ADR. Images use `<picture>` with pre-sized AVIF/WebP (320/640/1080), not `next/image`.
- **Frontend hosting:** a Next.js server container behind nginx, because the per-request CSP nonce in `src/proxy.ts` needs a server. Not Cloudflare Pages.
- **Backend:** Python 3.12, FastAPI async, Pydantic v2, SQLAlchemy 2.0 async + asyncpg, Alembic. Uses uv, Ruff (line length 130) and mypy strict.
- **Data:** PostgreSQL 16 with pgvector, pg_trgm, PostGIS and btree_gist. PgBouncer runs in transaction mode with the asyncpg statement cache off.
- **Jobs:** Celery + Redis (queues: `default`, `media`, `ai`) and exactly one Celery beat. Kafka only at Stage 4 scale.
- **Media:** Cloudflare R2 + CDN (`media.redstarvibe.com`), FFmpeg, Pillow/pyvips. SeaweedFS emulates R2 locally (not MinIO).
- **AI:** Cloudflare Workers AI by default (bge-m3 1024-dim embeddings, vision, Whisper), with Claude optional. The provider is chosen with `AI_PROVIDER=none|cloudflare|anthropic`. RAG is an in-house pipeline in `app/ai/rag` (plain SQL), **not LlamaIndex**. Vectors stay in pgvector (no Qdrant) until ~10M vectors or search p95 > 150 ms. No self-hosted GPU.
- **MCP:** official MCP Python SDK, served at `/mcp` behind the gateway (not a subdomain).
- **Payments:** Razorpay (Phase 6). **Calls:** LiveKit (Phase 7).
- **Edge/infra:** Cloudflare DNS/TLS Full (strict)/WAF/Turnstile/Tunnel. nginx is the only public entry point. Docker Compose runs on one VM at first. GitHub Actions + GHCR for CI/CD.
- **Observability:** OpenTelemetry, Prometheus, Grafana, Loki, Sentry, Uptime Kuma, PostHog.

## Architecture

The system is a **modular monolith**: one backend codebase and image, run as separate processes:

| Process | Runs |
|---|---|
| gateway | nginx: routes `/api/`, `/ws`, `/mcp`, `/rsv-raw/`, `/rsv-public/`, everything else to Next.js |
| web | Next.js SSR |
| api | gunicorn + uvicorn, `app.main:app`, REST under `/api/v1` |
| ws | WebSockets, Redis pub/sub between copies |
| mcp | `app.mcp.server:app` |
| worker | Celery |
| beat | Celery beat: counter flush (5 s), outbox relay, reminders, cleanup |
| migrate | one-shot Alembic before each deploy |

Only extract a module into its own service when metrics prove it needs to (chat, feed and media would go first).

### Target layout

```
apps/web/            Next.js app (src/app, features, components, hooks, lib, styles)
apps/backend/app/    api/v1, core, modules/<name>, ai, mcp, workers
apps/backend/migrations/
packages/api-types/  TS types generated from OpenAPI (@rsv/api-types)
infra/               docker, nginx, scripts, monitoring
docs/                adr/, runbooks/, api/, security/, product/, STATUS.md
```

### Backend module contract

Each `apps/backend/app/modules/<name>/` has these files:

- `router.py`: endpoints, input validation and `require_permission()`. **No business logic.**
- `schemas.py`: Pydantic request/response models.
- `service.py`: business rules, transactions, object-level authorization and outbox writes.
- `repository.py`: all SQL. **Always filter by tenant (`business_id` / `owner_id`).**
- `models.py`, `tasks.py`, `events.py`, `tests/`.

Routers call services, and services call repositories. Nothing skips a layer.

To wire a new module:
1. Include its router in `app/api/v1/router.py`.
2. Import its models in `app/models.py`.
3. Add its tasks in `app/workers/celery_app.py`.
4. Add its permissions to the permission map.

Existing tables stay in the `public` schema, and each new module gets its own Postgres schema.

## Non-negotiable rules

**Boundaries and events**
- A module never reads or writes another module's tables. It calls that module's service functions or reacts to its events. There are no cross-schema foreign keys and no circular dependencies. import-linter enforces this in CI.
- All async side effects go through the **transactional outbox** (`notify.outbox`). `emit()` keeps its name but inserts in the same DB transaction. Never use "commit, then emit".
- Events carry `event_id`, `type` (`module.action`), `version`, `occurred_at` and the entity id. Consumers are idempotent and record processed `event_id`s.

**Security**
- Authorization lives in the backend. There is one permission map in `app/core/permissions.py` (roles: `user`, `business`, `staff`, `admin`, `superadmin`).
- Routes check the permission, and services check object ownership. UI hiding is not security. Test IDOR with another user's object.
- Never bind request JSON directly to ORM models. Always use bound SQL parameters, never string-built SQL.
- Never log passwords, tokens, OTPs or full phone numbers. Never return stack traces or provider internals to clients.
- Superadmins are created only through `scripts/make_superadmin.py`. Every admin and staff action goes to an append-only `audit_log`.

**Data**
- Money is stored as integer **paise**, never floats.
- Times are stored as UTC `timestamptz` and shown in the user's timezone (default Asia/Kolkata).
- New primary keys use UUIDv7.
- Double booking is blocked by a Postgres `EXCLUDE USING gist` constraint on `(resource_id, slot)`. Inventory uses `UPDATE … WHERE stock >= qty`. Never rely on frontend checks for either.
- Migrations follow expand-then-contract: build indexes on big tables with `CREATE INDEX CONCURRENTLY`, and run backfills as batched Celery jobs. Restart PgBouncer after a column type change.
- Phone numbers and addresses are encrypted at field level.

**API**
- REST lives under `/api/v1` with cursor pagination only (`?cursor=…&limit=20`, never OFFSET on large tables).
- Every error uses one shape: `{"error": {"code", "message", "details", "request_id"}}`.
- Post, booking, order and payment creation take an `Idempotency-Key` header, stored for 24 h.
- OpenAPI is the contract. Run `make types` after schema changes; CI fails if `openapi.json` is stale.
- Every outbound call has a timeout (default 5 s) and retries with backoff and jitter.
- Auth uses a 15-min access token and a rotating 30-day refresh token, both in HttpOnly Secure SameSite=Lax `__Host-` cookies. Reusing an old refresh token revokes the whole token family. Mutations require `x-csrf-token` to match the `rsv_csrf` cookie.

**Media**
- The browser uploads directly to R2 with a 10-min presigned PUT. Large media **never passes through FastAPI**.
- The DB stores R2 keys, not URLs or binaries.
- The worker checks magic bytes, strips EXIF/GPS and re-encodes everything. Private files are served through signed GET URLs.

**AI**
- AI is optional and must degrade safely. Every AI path has a non-AI fallback (for example, keyword search or the hash-v1 embedding).
- The permission filter is applied **in SQL**; the prompt is never the security boundary.
- **Never index direct messages.** Treat retrieved and user text as untrusted.
- Redact PII before calling an external model.
- MCP tools call the same service layer as REST, and writes are **draft-only**.
- Prompts are versioned files (for example `app/ai/prompts/caption_v3.md`). Each AI feature has an eval set that runs in CI.
- Every embedding row records its model and version. Never compare vectors from different models.

**Scale**
- Processes are stateless. Heavy work runs in workers, never in the request path.
- Add replicas, partitions, Kafka, Kubernetes or microservices only after a measured need and an ADR.

**Memory**
- Always close DB sessions.
- Use one shared `httpx.AsyncClient` per process.
- Keep caches bounded and give every Redis key a TTL.
- Set Celery `worker_max_tasks_per_child`.
- No untracked `asyncio.create_task`.
- Every frontend `useEffect` returns a cleanup.

## Frontend rules

- Layouts are mobile-first and tested at 360, 768 and 1280 px. Phones get bottom tabs, tablets an icon rail, and desktop (1024 px and up) a side nav.
- Touch targets are at least 44 px. Target WCAG 2.2 AA.
- Public pages (`/`, `/{username}`, `/business/[slug]`, `/p/…`) are SSR with OG tags and a 1200×630 share image.
- The strict CSP nonce is set in `src/proxy.ts`. New third-party origins must be added to the policy.
- Budgets: LCP < 2.5 s on 4G, INP < 200 ms, CLS < 0.1, initial JS < 170 KB gzip, Lighthouse mobile 90+.
- Ship Hindi and English from day one.
- Design tokens: Star Red `#C8102E` (dark `#9B0C23`, soft `#FDF2F3`), fonts Plus Jakarta Sans + Noto Sans Devanagari, 4 px spacing grid. No raw colors or sizes in pages.

## Commands (planned, not yet in repo)

The Blueprint defines these commands. Check the Makefile and scripts before you rely on them. If a command doesn't exist, document the real equivalent instead of inventing one.

```
python scripts/bootstrap_env.py   # first run: writes .env with fresh secrets
make up                           # build + start + migrate → http://localhost:8080 (gateway)
make seed                         # demo data
make logs / make down
make test / make lint / make test-web / make e2e / make types / make load
```

On Windows, run docker compose from PowerShell, or set `MSYS_NO_PATHCONV=1` in Git Bash. Don't export `.env` in Git Bash, because that breaks `MEDIA_PUBLIC_BASE`. Install make with `winget install ezwinports.make`.

Run backend tests against a separate test database, never the running app DB.

## Roadmap

| Phase | Scope | Exit criteria |
|---|---|---|
| 0 | Repo audit, feature verification matrix, `docs/STATUS.md`, ADRs | New dev can run it; baseline known |
| 1 (3 wk) | Outbox, permission map, audit log, rate limits, backups + restore drill, monitoring, staging, CI/CD | Restore drill passes; staging deploy automatic; alerts reach team |
| 2 (4 wk) | Business services/hours, slots, booking (exclusion constraint), calendar, reminders, reviews, PostGIS near-me, inbox, Quick Shop | 20 businesses take real bookings for 2 weeks |
| 3 (3 wk) | Cards, albums, slideshows, referrals, QR, OG share | 10% of active users share a card weekly |
| 4 (5 wk) | Comments, follow requests, block/mute, stories, DMs, groups, voice notes, reels | Day-7 retention measured and improving |
| 5 (4 wk) | Event packages, vendors, availability, shop products, orders | 5 event companies + 10 shops live |
| 6 (3 wk) | Razorpay, deposits, plans, boosts, payouts, GST invoice | First paid plan + advance payment reconciled |
| 7 (4 wk) | LiveKit calls, AI captions/alt text/subtitles/translation, business assistant | AI cost per active user under budget |
| 8 | Scale (metrics-triggered only) | Scaling triggers met |

The 29-week schedule starts Mon 9 Nov 2026, with a launch review on Fri 28 May 2027. Wellbeing, school and hospital modules and live streaming are backlog items and need separate approval. A hospital module would need a separate DB and legal review. The minimum age is **18+** until a legally reviewed parental-consent flow exists.

## Definition of Done

A feature is done only when all of these hold:
- Tests pass: unit, plus integration on real Postgres + Redis. Authorization is tested with another user's object.
- The migration is reviewed and backward compatible.
- The router, models and tasks are wired in.
- Events go through the outbox, and consumers are idempotent.
- OpenAPI is updated and `make types` has been run.
- It works at 360, 768 and 1280 px, with accessibility checked.
- Logs carry a `request_id`, and metrics and alerts exist where needed.
- `docs/STATUS.md` is updated, and an ADR is written if an architecture choice was made.

Coverage: 60%+ per module, and 80% for auth, booking, payments and rewards.
