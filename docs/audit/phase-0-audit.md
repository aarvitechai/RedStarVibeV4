# Phase 0 — Repository Audit

Date: 2026-11-16 · Branch: `dev` · Baseline: Blueprint v4.0, Execution Plan v1.0

## 1. What the repository contained before Phase 0

| Item | Found |
|---|---|
| Application code (frontend or backend) | **None** |
| Planning docs | Blueprint v4 (.docx), Execution Plan (.md), Technical Architecture v1 (.docx), Master Implementation Plan (.docx) |
| `CLAUDE.md` | Added on 2026-11-16 from the documents above |
| README, `.env.example`, Docker, Makefile, migrations, CI | None |
| Secrets committed | None found (history had 3 commits, all docs) |
| Branches | `main`, `dev`, `staging`, `production` (all identical) |

The Blueprint describes a CLAUDE.md "of the running code" and features that are "already built". That code is **not in this repository**. Per the Execution Plan rule "Treat the repository as evidence", every such feature is recorded as `not implemented` (see ADR 0017).

## 2. Local toolchain found on the developer machine

| Tool | Version | Note |
|---|---|---|
| Docker / Compose | 29.9.2 / v5.6.1 | Docker Desktop engine was **not running** during the audit |
| Node / npm | 24.13.0 / 11.6.2 | OK (images use Node 22 LTS) |
| Python | 3.11.6 | Blueprint requires 3.12; images use 3.12. Local tests run on 3.11 |
| make, uv | missing | `winget install ezwinports.make`; uv optional |

## 3. Feature verification matrix

Status values: `working`, `partial`, `broken`, `not implemented`, `unknown`.

| Feature (Blueprint 3.1 "already built") | Status | Evidence |
|---|---|---|
| Signup / login / logout, cookies + CSRF | not implemented | no code |
| Google sign-in, Turnstile, breached-password check | not implemented | no code |
| Presigned media upload, AVIF/WebP, HLS, text overlay | not implemented | no code |
| Feed fan-out, celebrity merge, buffered counters, For You | not implemented | no code |
| Likes + notifications via event dispatcher | not implemented | no code |
| Hybrid search (tsvector + pgvector + RRF) | not implemented | no code |
| RAG assistant with tenant filter | not implemented | no code |
| Image moderation | not implemented | no code |
| MCP server (draft-only) | not implemented | no code |
| Public business page `/business/[slug]` | not implemented | no code |
| Admin panel, roles, demo data | not implemented | no code |

## 4. What Phase 0 added (verified)

| Item | Verification |
|---|---|
| Monorepo layout (`apps/backend`, `apps/web`, `packages/api-types`, `infra`, `docs`, `scripts`) | in tree |
| FastAPI app factory, settings (refuses weak secrets in staging/prod), request-id middleware, one error shape, `/health/live`, `/health/ready`, `/api/v1/meta` | 9 pytest tests pass; ruff + mypy strict clean |
| Alembic with migration `0001` (citext, pg_trgm, btree_gist, postgis, vector) | not yet run — needs Docker |
| Celery app: queues default/media/ai, acks_late, worker recycling | imports cleanly |
| Next.js 16 + React 19 app, strict per-request CSP nonce in `src/proxy.ts`, design tokens, Button primitive | build passes; vitest passes; lint clean; all 9 rendered scripts carry the nonce |
| nginx gateway on :8080 routing `/api/`, `/health/`, web | config written; not yet run — needs Docker |
| docker-compose: gateway, web, api, migrate, worker, beat, db (Postgres 16 + PostGIS + pgvector), redis | not yet run — needs Docker |
| `scripts/bootstrap_env.py`, Makefile, `.env.example` | bootstrap verified |
| OpenAPI export + generated `@rsv/api-types` | generated; CI checks staleness |
| GitHub Actions CI, Dependabot, PR template | written; first run happens on push |
| ADRs 0001–0017 | `docs/adr/` |

## 5. Initial risk register

| Risk | Impact | Mitigation | Owner |
|---|---|---|---|
| Blueprint assumes existing code that is absent | High: timeline and scope underestimated | ADR 0017; re-estimate Phase 1 | Tech lead |
| Docker stack not yet run end-to-end | Medium | Start Docker Desktop; run `make up`; record result in STATUS.md | Developer |
| Local Python 3.11 vs 3.12 target | Low | CI and images use 3.12 | Developer |
| Branch flow differs from Blueprint (ADR 0016 Proposed) | Medium: deploy workflow design | Product owner to confirm ADR 0016 | Product owner |
| No hosting accounts yet (VM, Cloudflare, R2, domain DNS) | High: no staging URL possible | Create accounts in Phase 1 week 2 | DevOps |
| Pilot city and trades not chosen | High: Phase 2 cannot validate | Decide before Phase 2 | Product owner |
| Legal review (DPDP, age, payments) | High | Engage counsel before public launch | Product/legal |

## 6. Prioritised Phase 1 backlog

1. Accounts: users table (UUIDv7, citext username, reserved names), Argon2id, signup/login/logout, rotating refresh tokens with family revocation, CSRF double-submit.
2. Permission map + `require_permission()`; object-level checks; IDOR test pack.
3. Append-only audit log.
4. Transactional outbox + relay + idempotent consumers + dead letter.
5. Rate limits (Redis sliding window) for login/signup.
6. Backups (wal-g / nightly pg_dump to R2) + restore drill script.
7. Staging environment, deploy workflow, production approval gate.
8. Observability: structured logs (done), Sentry, metrics, alerts.

## 7. Exit criteria check

| Criterion | Status |
|---|---|
| A new developer can run the project with documented steps | Documented in `docs/setup.md`; full Docker run pending Docker Desktop |
| Baseline build/test status known | Yes: backend 9/9, web build + tests pass |
| Existing features verified rather than assumed | Yes: none exist; matrix above |
| Critical blockers and risks recorded and assigned | Yes: section 5 |
