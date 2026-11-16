# RedStarVibe — Development Execution Plan

**Document type:** Product + Engineering Execution Plan  
**Plan version:** 1.0  
**Baseline architecture:** RedStarVibe Production Blueprint v4.0 (3 November 2026)  
**Status:** Execution baseline — validate repository state before marking any item complete  
**Primary goal:** Build RedStarVibe phase by phase as a secure, maintainable, scalable platform without prematurely splitting the system into microservices.

---

## 1. How to Use This Plan

This document is the working execution guide for product, frontend, backend, database, QA, DevOps, security, AI, and operations.

1. Read Sections 1–8 before starting implementation.
2. Create or update the project status file (`docs/STATUS.md`) and Architecture Decision Records (`docs/adr/`).
3. Execute phases in order. Do not start the next major phase only because the calendar says so; satisfy the phase exit criteria with real users and measurable evidence.
4. Break every work item into an issue with an owner, estimate, dependencies, acceptance criteria, tests, and documentation.
5. Keep this file current. Mark an item complete only when its code, tests, security review, documentation, deployment, and operational checks are complete.
6. Treat the repository and production telemetry as evidence. A feature described as “already built” in source documents is not automatically verified in the running application.

### 1.1 Source-of-truth policy

The **RedStarVibe Production Blueprint v4.0** is the current product and architecture source of truth. It explicitly replaces earlier plan documents and resolves earlier technology disagreements. The older Technical Architecture and Master Implementation Plan remain useful for background and feature intent, but their conflicting implementation choices must not silently override Blueprint v4.0.

When code and this plan differ:

- Inspect the actual repository and `CLAUDE.md` / project instructions.
- Confirm whether the difference is intentional.
- Record the decision in `docs/adr/`.
- Update this plan and the relevant implementation docs.
- Never perform a risky migration simply to make code match a document without an approved ADR.

### 1.2 Important decisions already resolved by Blueprint v4.0

Use these decisions as the baseline:

| Area | Current decision |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript strict |
| UI | Hand-written reusable UI primitives and CSS variables; do not introduce a component framework without an ADR |
| Frontend hosting | Next.js server behind the gateway/Nginx, not a static-only Cloudflare Pages deployment |
| Backend | Python 3.12, FastAPI, Pydantic v2 |
| Database | PostgreSQL 16 with pgvector, pg_trgm, PostGIS, btree_gist |
| ORM/migrations | SQLAlchemy 2 async, asyncpg, Alembic |
| Jobs | Celery + Redis; add Kafka only if a later measured scale stage justifies it |
| Media | Cloudflare R2 + CDN; direct presigned uploads; FFmpeg and image processing workers |
| Search | PostgreSQL keyword + pgvector hybrid retrieval with Reciprocal Rank Fusion (RRF) |
| Embeddings | 1024 dimensions for the selected embedding model; record model/version on each vector |
| RAG | In-house retrieval pipeline with SQL permission filtering; do not assume the older LlamaIndex design |
| AI inference | Cloudflare Workers AI by default, optional Claude provider; no self-hosted GPU at launch |
| Deployment | One VM / modular monolith initially, then add replicas based on metrics |
| Event delivery | Transactional outbox; do not rely on “commit then emit” |
| Storage architecture | Cloudflare R2 is the media object store. If SeaweedFS or another storage technology exists in the repository for a different purpose, document its exact role in an ADR before using or removing it. |

---

## 2. Product Vision and Scope

RedStarVibe is a combined social and business platform. A small business or skilled worker can create a public page, share its link, publish content, receive enquiries and bookings, manage products or event packages, and communicate with customers. Social content, stories, chat, cards, albums, and AI-assisted tools help users discover and return to the platform.

### 2.1 Main user groups

- **Visitor:** discovers public profiles, posts, business pages, services, products, and shared cards.
- **Personal user/customer:** creates a profile, follows people, publishes posts, messages, books services, orders products, and manages privacy.
- **Business owner:** manages a public business page, services, working hours, staff, bookings, reviews, products, orders, and business communications.
- **Business staff:** performs only the tasks explicitly granted by the business owner.
- **Creator:** publishes content, creates cards/albums, builds an audience, and may later receive tips or creator benefits.
- **Event organizer/vendor:** publishes packages, invites vendors, manages availability, and coordinates event bookings.
- **Support/moderation staff:** reviews reports and support cases with scoped permissions and audit trails.
- **Admin/superadmin:** operates platform-level moderation, verification, configuration, and administration.
- **AI assistant/agent:** helps users search and draft actions through permission-checked services; it must not bypass application authorization.

### 2.2 Product principles

1. Business utility and customer value come before adding large numbers of social features.
2. Launch in one city and a small number of service categories.
3. Onboard 20–30 real businesses in person before broad expansion.
4. Make the public business page and booking workflow genuinely useful every day.
5. Keep social, AI, and media features optional and degrade gracefully when providers are unavailable.
6. Protect user privacy, business tenancy, and user-generated content by default.
7. Do not scale infrastructure ahead of product usage and measured bottlenecks.

### 2.3 Product areas

- Identity, profile, account safety, and public usernames.
- Business pages, services, working hours, staff, and local discovery.
- Posts, media, feed, follows, likes, comments, stories, reels, and collections.
- Bookings, calendars, reminders, reviews, quotations, and business inbox.
- Digital greeting cards, festival frames, albums, slideshows, referrals, and QR/share pages.
- Event organizers, packages, vendors, availability, and event bookings.
- Shop catalogs, inventory, orders, order status, and customer communication.
- Payments, deposits, subscriptions, promotion, payouts, and invoices.
- Notifications across in-app, web push, email, SMS, and WhatsApp where enabled.
- AI-assisted search, RAG assistant, moderation, captions, alt text, subtitles, translation, and MCP tools.
- Admin, moderation, support, analytics, and operational dashboards.
- Later backlog: wellbeing/growth modules, school/hospital modules (only after separate legal and architecture review), live streaming, and larger communities.

---

## 3. Success Measures and Non-Functional Requirements

Targets below are planning goals from the production blueprint, not claims that the current system already meets them. Establish baseline measurements and report actual values.

### 3.1 Product and adoption targets

| Milestone | Target / exit evidence |
|---|---|
| Business workflow validation | 20 businesses take real bookings for at least 2 weeks |
| Viral card validation | 10% of active users share a card in a week |
| Social quality | Day-7 retention is measured and improving |
| Events and shop validation | 5 event companies and 10 shops are live |
| Monetization validation | First paid plan and first advance payment completed and reconciled |
| AI cost control | AI cost per active user remains under the approved budget |
| Scale readiness | Scaling triggers in Section 18 are met with production telemetry |

### 3.2 Performance and reliability targets

| Metric | Target |
|---|---|
| API latency | p95 below 200 ms for normal API requests, excluding explicitly long-running work |
| Largest Contentful Paint | below 2.5 seconds on a representative 4G mobile connection |
| Interaction to Next Paint | below 200 ms |
| Cumulative Layout Shift | below 0.1 |
| Initial JavaScript | below 170 KB gzip where applicable |
| Feed first paint | target below 1.5 seconds |
| Chat delivery | target below 500 ms under normal operating conditions |
| Availability | 99.9% launch target; improve toward 99.95% at scale |
| Recovery Point Objective | under 5 minutes where the selected backup/replication design supports it |
| Recovery Time Objective | under 1 hour |
| API error budget | define per service tier and review monthly |

### 3.3 Planning capacity

Recheck capacity quarterly using real traffic and load tests.

| Measure | Initial planning stage | Large-scale planning stage |
|---|---:|---:|
| Registered users | 10K | 1M |
| Daily active users | 3K | 300K |
| Peak API requests/second | ~30 | ~3,000 |
| New posts/day | 1K | 100K |
| Media stored/month | ~50 GB | ~5 TB |
| Bookings/day | 200 | 20K |
| Concurrent WebSockets | 300 | 50K |

These are capacity-planning reference points, not guaranteed limits for a single VM.

---

## 4. Delivery Method, Team Roles, and Governance

### 4.1 Recommended delivery roles

One person may hold multiple roles in a small team, but each responsibility must be assigned.

- Product owner: scope, user validation, prioritization, acceptance.
- Technical lead: architecture, ADRs, code review, engineering standards.
- Frontend engineer: Next.js app, responsive UI, PWA, accessibility.
- Backend engineer: FastAPI modules, domain services, APIs, database.
- QA engineer: test strategy, automation, regression, release sign-off.
- DevOps/SRE: environments, CI/CD, monitoring, backups, incident response.
- Security/privacy owner: threat reviews, permissions, data retention, legal coordination.
- Design owner: user journeys, design system, accessibility and content language.
- Business operations owner: pilot onboarding, feedback, support and adoption.

### 4.2 Work item template

Every engineering ticket must contain:

- Problem and user outcome.
- Scope and explicit non-goals.
- Dependencies and impacted modules.
- API/UI/database changes.
- Authorization and privacy implications.
- Acceptance criteria written as observable outcomes.
- Unit, integration, end-to-end, and regression tests.
- Migration and rollback plan where applicable.
- Logging, metrics, alerts, and support implications.
- Documentation updates.
- Owner, reviewer, estimate, and target phase.

### 4.3 Definition of Ready

A task is ready when its user outcome, requirements, design/API contract, dependencies, acceptance criteria, and test approach are understood. Unknown legal, payment, provider, or security decisions must be raised before implementation.

### 4.4 Definition of Done

A feature is done only when:

- Code follows the module boundaries and coding standards.
- Input validation and authorization are enforced server-side.
- Tenant/object ownership checks exist in service methods.
- Database migrations are reversible or have a documented forward-fix strategy.
- Unit and integration tests pass; end-to-end tests cover critical user journeys.
- Accessibility and responsive behavior are checked.
- Errors are handled without leaking secrets or stack traces.
- Logs, metrics, and alerts exist for critical paths.
- API/OpenAPI and generated frontend types are current.
- Security, privacy, and abuse cases are reviewed.
- Documentation, runbooks, and `docs/STATUS.md` are updated.
- Staging verification and product acceptance are complete.
- Rollback/recovery procedure is known.

---

## 5. Target Architecture

### 5.1 Architectural style

Use a **modular monolith**: one backend codebase and deployable image, organized into well-defined domain modules. Run different process types (API, WebSocket, MCP, workers, scheduler) independently so each can scale according to its workload. Extract a module into a separate service only when measured throughput, isolation, release cadence, or reliability needs justify it.

### 5.2 High-level request and data flow

```text
Browser / PWA (mobile, tablet, desktop)
        |
Cloudflare DNS / TLS / WAF / CDN / DDoS / edge limits
        |
Cloudflare Tunnel
        |
Nginx gateway (only public application entry)
        |
        +--> Next.js web / SSR
        +--> FastAPI REST API (/api/v1)
        +--> WebSocket process (/ws)
        +--> MCP process (/mcp)
        |
Private application network
        |
        +--> PostgreSQL 16 (+ pgvector, PostGIS, pg_trgm)
        +--> Redis (cache, queues, pub/sub, counters, rate limits)
        +--> Celery workers (default, media, AI queues)
        +--> Celery beat (one active scheduler)
        |
Cloudflare R2 + CDN (media object storage)
External providers: LiveKit, Razorpay, email/SMS/WhatsApp, AI APIs
```

### 5.3 Non-negotiable architecture rules

1. The browser never sends large media payloads through the FastAPI application. Use short-lived presigned uploads directly to R2.
2. Every application process is stateless. Persistent state belongs in PostgreSQL, Redis, or R2.
3. PostgreSQL, Redis, workers, and internal services stay on a private network.
4. Nginx is the only public application entry point.
5. Slow work (media processing, AI, feed fan-out, notifications, reminders, exports) runs asynchronously.
6. A module owns its tables and business rules. Other modules call its service interface; they do not write its tables.
7. Use transactional outbox events for reliable asynchronous work.
8. Enforce authorization in the backend service layer and SQL query filters. UI hiding is not security.
9. Use cursor pagination for large feeds and lists; avoid large OFFSET scans.
10. Add infrastructure complexity only when telemetry justifies it.

### 5.4 Process responsibilities

| Process | Responsibility | Scaling dimension |
|---|---|---|
| gateway | Nginx routing and TLS boundary | gateway capacity / redundancy |
| web | Next.js SSR and frontend | CPU, memory, request rate |
| api | FastAPI REST endpoints | CPU, request rate |
| ws | WebSocket connections and real-time events | concurrent connections |
| mcp | MCP tools and agent requests | tool request rate |
| worker | Celery jobs: default, media, AI | queue depth and job duration |
| beat | scheduled jobs and outbox relay | exactly one active scheduler with safe failover |
| migrate | one-shot Alembic migration process | run once per deployment |

### 5.5 Domains and routing

- `redstarvibe.com` and `www.redstarvibe.com`: web application.
- `/api/v1`: REST API.
- `/ws`: WebSocket connections.
- `/mcp`: MCP endpoint.
- `/rsv-raw/` and `/rsv-public/`: only if retained by the current implementation and reviewed.
- `media.redstarvibe.com`: R2 media CDN.
- `stage.redstarvibe.com`: staging, protected by Cloudflare Access.
- `stage-media.redstarvibe.com`: staging media bucket.

Use Cloudflare SSL mode **Full (strict)**. Use Cloudflare Tunnel so the VM does not expose application ports directly to the public internet.

---

## 6. Technology Stack and Engineering Standards

### 6.1 Frontend

- Next.js 16, React 19, TypeScript strict.
- Hand-written UI primitives with design tokens and CSS variables for light/dark themes.
- TanStack Query for server state, caching, and invalidation.
- Zustand only for client-side state that genuinely needs shared state.
- React Hook Form + Zod for forms and client validation.
- API types generated from OpenAPI (`@rsv/api-types`).
- Responsive PWA for 360 px mobile, 768 px tablet, and 1280 px desktop.
- Hindi and English first; other Indian languages can follow.
- SSR for public profiles, business pages, posts, and share previews.
- PWA installability, offline shell, web push, and data saver mode.

### 6.2 Backend

- Python 3.12, FastAPI async, Pydantic v2.
- SQLAlchemy 2.0 async, asyncpg, Alembic.
- Celery + Redis for background jobs and scheduled work.
- Official MCP Python SDK.
- OpenAPI as the API contract.
- Ruff/formatting and type checks as part of CI.

### 6.3 Data and infrastructure

- PostgreSQL 16: relational source of truth, pgvector, pg_trgm, PostGIS, btree_gist.
- PgBouncer transaction pooling; configure asyncpg statement cache appropriately for transaction pooling.
- Redis: cache, rate limits, session-related ephemeral state, pub/sub, queue, buffered counters.
- Cloudflare R2 + CDN for media.
- FFmpeg and Pillow / pyvips for media transformation.
- LiveKit for WebRTC calling when Phase 7 is approved.
- Cloudflare Workers AI by default; optional Claude API provider.
- Docker and Docker Compose for reproducible environments.
- GitHub Actions and GHCR for CI/CD and image distribution.
- OpenTelemetry, Prometheus, Grafana, Loki, Sentry, and Uptime Kuma for observability.

### 6.4 Code conventions

- Python and TypeScript strict typing; avoid untyped escape hatches.
- Small, cohesive modules and functions.
- No business logic in route handlers or UI components.
- No raw SQL string concatenation.
- No direct cross-module table writes.
- Use dependency injection for providers and external clients.
- Centralize configuration and feature flags.
- Avoid premature abstractions; abstract repeated, stable behavior rather than speculative future needs.
- Keep secrets out of source control and logs.
- Use conventional commits or an equivalent consistent commit format.
- Require pull request review for production changes.

---

## 7. Repository and Module Organization

Adapt names to the existing repository rather than restructuring blindly. The following is the target organization.

### 7.1 Suggested repository layout

```text
redstarvibe/
├── apps/
│   ├── web/
│   │   ├── src/
│   │   │   ├── app/
│   │   │   ├── features/
│   │   │   ├── components/
│   │   │   ├── hooks/
│   │   │   ├── lib/
│   │   │   └── styles/
│   │   └── tests/
│   └── backend/
│       ├── app/
│       │   ├── api/v1/
│       │   ├── core/
│       │   ├── modules/
│       │   │   ├── accounts/
│       │   │   ├── profiles/
│       │   │   ├── posts/
│       │   │   ├── feed/
│       │   │   ├── social/
│       │   │   ├── media/
│       │   │   ├── business/
│       │   │   ├── booking/
│       │   │   ├── notifications/
│       │   │   ├── chat/
│       │   │   ├── cards/
│       │   │   ├── events/
│       │   │   ├── shop/
│       │   │   ├── payments/
│       │   │   ├── search/
│       │   │   ├── ai/
│       │   │   ├── moderation/
│       │   │   └── admin/
│       │   ├── workers/
│       │   └── mcp/
│       ├── migrations/
│       └── tests/
├── packages/
│   └── api-types/
├── infra/
│   ├── docker/
│   ├── nginx/
│   ├── scripts/
│   └── monitoring/
├── docs/
│   ├── adr/
│   ├── runbooks/
│   ├── api/
│   ├── security/
│   ├── product/
│   └── STATUS.md
├── docker-compose.yml
├── Makefile
└── README.md
```

### 7.2 Backend module contract

Every backend domain module follows the same responsibility boundaries:

| File | Responsibility |
|---|---|
| `router.py` | HTTP/WS endpoints, request validation, permission dependency, response mapping; no business rules |
| `schemas.py` | Pydantic request and response contracts |
| `service.py` | Business rules, transactions, object authorization, outbox writes |
| `repository.py` | SQL queries and persistence; tenant filters always included |
| `models.py` | SQLAlchemy models owned by this module |
| `tasks.py` | Celery tasks owned by this module |
| `events.py` | Event names, versions, payload schemas |
| `tests/` | Unit, integration, authorization, and contract tests |

To register a new module: include its router in the API router, register its models in the metadata/migration setup, register its Celery tasks, add permissions, and document emitted/consumed events.

### 7.3 Module communication

- Direct service call: only when the caller needs the answer immediately (for example, checking a block before sending a message).
- Domain event: notifications, feed fan-out, search indexing, analytics, reminders, and other eventual work.
- Every event has `event_id`, `type`, `version`, `occurred_at`, entity identifier, and validated payload.
- Consumers are idempotent and record processed event IDs.
- Do not create circular module dependencies. If two modules need each other, define a clear owner for the shared workflow or publish an event.

---

## 8. Database and Data Governance

### 8.1 Core database rules

1. PostgreSQL is the source of truth.
2. Use UUIDv7 for new primary identifiers where supported by the current codebase and migration plan.
3. Use `timestamptz` and store UTC. Display in the user's timezone; default application timezone is Asia/Kolkata.
4. Store money as integer paise, never floating-point values.
5. Every business-owned record includes `business_id`; every user-private AI chunk includes `owner_id` or an equivalent explicit access scope.
6. Every repository query applies tenant and visibility filters in SQL.
7. Keep module table ownership clear; avoid cross-schema foreign keys if following the Blueprint's schema ownership pattern.
8. Add indexes for foreign keys and hot filter/order columns; use `EXPLAIN ANALYZE` for performance-sensitive queries.
9. Soft-delete with `deleted_at` where recovery/audit requirements justify it; hard purge after the documented retention period.
10. Use expand-then-contract migrations for zero-downtime deployment.
11. Partition high-volume tables such as messages, notifications, and analytics by month when the operational threshold is reached.
12. Keep sensitive phone/address fields encrypted at field level where required.
13. Never index direct messages into the RAG knowledge base.

### 8.2 Main domain schemas and table groups

| Domain/schema | Main entities | Notes |
|---|---|---|
| accounts | users, sessions, MFA factors, login events, audit log | append-only audit log; session rotation |
| profiles | profiles, usernames, follows, blocks, mutes | reserved usernames; privacy state |
| posts | posts, post_media, likes, comments, saves | visibility and moderation state |
| feed | timelines, fanout state, counters | Redis for hot timeline/counters; DB source data |
| media | assets, upload intents, renditions | store R2 object keys, not binary media |
| business | businesses, services, hours, staff, reviews, replies | business tenancy and PostGIS location |
| booking | resources, availability, bookings, booking history | DB constraint prevents overlapping bookings |
| notifications | outbox, notification records, delivery attempts, preferences | partition high-volume records as needed |
| chat | conversations, members, messages, receipts | messages monthly partitioned; never RAG-index |
| cards | templates, renders, albums, slideshows | store R2 keys; idempotent render jobs |
| events | packages, package items, vendors, invitations, event bookings | vendor availability follows booking constraints |
| shop | products, inventory, orders, order items, status history | prevent overselling atomically |
| payments | payments, refunds, plans, subscriptions, webhook events, payouts | provider event ID unique; paise amounts |
| search/AI | embeddings, chunks, AI usage, indexing jobs | model/version stored with vectors; tenant filters |
| moderation | reports, review queue, decisions, appeals | auditable actions and evidence retention |
| admin/support | tickets, escalations, configuration changes | strict staff scopes and audit |

### 8.3 Booking integrity

- Use PostgreSQL `btree_gist` and a range/exclusion constraint to prevent overlapping active bookings for the same resource.
- Define the resource model (person, vehicle, room, service slot) before implementation.
- Use `pending`, `confirmed`, `done`, `cancelled`, and `expired` or a formally approved equivalent state machine.
- Validate business hours, service duration, buffers, timezone, cancellation policy, and staff/resource availability.
- Use an idempotency key on booking creation.
- Never rely only on a frontend availability check to prevent double booking.
- Add concurrency tests that attempt to book the same slot simultaneously.

### 8.4 Inventory integrity

- Decrement inventory atomically with a conditional update (`stock >= requested_quantity`).
- Use a transaction for order creation and stock reservation.
- Define cancellation, payment timeout, refund, and stock-restoration behavior.
- Add concurrent order tests to prove no overselling.

### 8.5 Migration policy

- One migration per coherent schema change.
- Review generated Alembic SQL before merge.
- Prefer additive nullable columns, backfills, dual-read/write if necessary, then removal in a later release.
- Never rename/drop a live column in the same release that stops using it.
- Back up before high-risk migrations.
- Test migration and rollback/forward-fix on a production-like staging copy.
- Restart PgBouncer after column type changes if required by the chosen pooling configuration.
- Document long-running migrations and lock impact.

---

## 9. API and Integration Standards

### 9.1 REST contract

- Prefix all APIs with `/api/v1`.
- A breaking contract change requires a planned version transition, not an unannounced field removal.
- OpenAPI is the contract; generated frontend types must be updated with `make types`.
- CI must fail if generated API types or committed OpenAPI artifacts are stale.
- Use cursor pagination: `?cursor=...&limit=20`.
- Use a consistent error shape:

```json
{
  "error": {
    "code": "stable_machine_code",
    "message": "Safe user-facing message",
    "details": {},
    "request_id": "correlation-id"
  }
}
```

- Never return stack traces, secrets, SQL details, or internal provider responses to clients.
- Every outbound network request has a timeout (5 seconds by default unless the integration needs a documented alternative) and bounded retries with exponential backoff and jitter.
- Use `Idempotency-Key` on post creation, booking creation, order creation, and payment initiation.
- Persist the idempotency key and replayable response for the documented retention window (Blueprint baseline: 24 hours).

### 9.2 Authentication contract

- Short-lived access token: 15 minutes.
- Rotating refresh token: 30 days, stored in secure HttpOnly cookies.
- Cookies: `HttpOnly`, `Secure`, `SameSite=Lax`, and `__Host-` prefix where applicable.
- Mutating requests require CSRF validation: `x-csrf-token` must match the CSRF cookie.
- Refresh-token reuse revokes the token family.
- Google OAuth uses state and PKCE.
- Admin, superadmin, and staff accounts require MFA.

### 9.3 Webhooks

- Verify provider signatures before processing.
- Store provider event IDs with a unique constraint.
- Make webhook handlers idempotent.
- Acknowledge quickly and enqueue slow work.
- Keep raw payloads only as long as required and redact sensitive data from logs.
- Provide replay/reconciliation tools restricted to authorized operators.

---

## 10. Frontend Product and UX Plan

### 10.1 Navigation and page families

- Public: home/discovery, `/{username}`, `/business/[slug]`, `/p/[post-or-share-id]`, shared card and album pages.
- Authentication: signup, login, recovery, MFA setup.
- Personal: feed, profile edit, create post, notifications, saved collections, settings, privacy, account safety.
- Business: dashboard, public page editor, services, working hours, staff, booking calendar, bookings, reviews, inbox, products, orders, analytics.
- Events: organizer dashboard, packages, vendor directory/invites, event bookings.
- Creator: card templates, albums, slideshow, creator profile and future monetization.
- Admin: moderation queue, reports, user/business verification, support, system health and audit views.

### 10.2 Responsive behavior

- Mobile under 640 px: bottom tab navigation and touch-first layouts.
- Tablet: compact icon rail or responsive navigation.
- Desktop 1024 px and above: side navigation plus content panel.
- Touch targets at least 44 × 44 px.
- Support keyboard navigation, visible focus, semantic headings, labels, and accessible dialogs.
- Follow WCAG 2.2 AA as the target.
- Design empty, loading, success, error, offline, permission-denied, and retry states for every important screen.

### 10.3 Design system

Create a single source of truth for:

- Color tokens and semantic states.
- Typography scale and multilingual font fallback.
- Spacing, radii, shadows, borders, and elevation.
- Breakpoints and layout widths.
- Buttons, inputs, selects, dialogs, dropdowns, cards, tabs, navigation, toast, skeletons, tables, upload controls, and media previews.
- Light and dark themes.
- Icon usage and illustration rules.
- Accessibility states and reduced motion.

Avoid one-off styling that creates inconsistent pages. Reusable components must remain small and composable.

### 10.4 Frontend performance

- Serve responsive AVIF/WebP image variants at 320/640/1080 widths.
- Set image width and height to prevent layout shifts.
- Lazy-load below-the-fold media.
- Use SSR for shareable public pages and correct Open Graph metadata.
- Keep the initial JavaScript budget under 170 KB gzip as the target.
- Use optimistic UI only when rollback and error feedback are implemented.
- Avoid unbounded client caches and long-lived event listeners.
- Profile real mobile devices and slow networks.

---

## 11. Security, Privacy, Trust, and Compliance

Security is part of every phase, not a separate final sprint.

### 11.1 Identity and account protection

- Password hashing with Argon2id.
- Minimum password length and breached-password checks.
- Access/refresh token rotation and reuse detection.
- MFA with TOTP and passkeys; mandatory for privileged accounts.
- Login activity, new-device alerts, and log out other devices.
- Phone OTP only after rate limits, provider cost, and abuse protections are ready.
- Account recovery must not weaken MFA or enable account takeover.

### 11.2 Authorization

- Maintain one central permission map in code.
- Route-level permission check plus service-level object ownership check.
- Every business staff request is scoped to the correct `business_id`.
- Every admin/staff action writes to an append-only audit log.
- Create superadmins only through a controlled script/process.
- Test IDOR/BOLA by attempting to access another user's or business's objects.
- Never trust role names or IDs supplied by the client.

### 11.3 Abuse and rate limits

Baseline limits from the production blueprint should be configurable and tuned with real abuse data:

| Action | Initial control |
|---|---|
| Login | 5/minute, then progressive backoff; IP + account |
| OTP send | 3 per 10 minutes; phone + IP |
| Signup | Turnstile and 10/hour/IP |
| Create post | 30/hour/user |
| DM send | 60/minute/user, stricter for new accounts |
| Create booking | 10/hour/customer |
| Upload URL | 60/hour/user |
| MCP calls | 60/minute/token |
| Public API | Cloudflare edge limits |

### 11.4 OWASP-oriented controls

- BOLA/IDOR: object authorization in every service.
- Injection: bound parameters only.
- XSS: React escaping, sanitized rich text, strict CSP nonce.
- CSRF: SameSite cookies plus CSRF token.
- SSRF: allow-list external fetches and block private IP ranges.
- Upload: size/type limits, magic-byte validation, re-encoding, EXIF/GPS stripping, malware scanning where appropriate.
- Mass assignment: dedicated Pydantic input schemas; never bind request JSON directly to ORM models.
- Bots/spam: Turnstile, rate limits, new-account restrictions, moderation signals.
- Secrets: never commit secrets; use a secret manager or SOPS + age; separate per environment and rotate.
- Dependencies: Dependabot, `pip-audit`, `npm audit`, Trivy, CodeQL.
- Headers: HSTS, CSP, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, `frame-ancestors 'none'`.

### 11.5 Privacy and data governance

- Publish clear privacy policy, terms, community rules, and retention policy before public launch.
- Obtain consent for notifications, marketing, and optional AI processing.
- Minimize personal data and redact PII before external AI calls.
- Define export, correction, deletion, and account closure workflows.
- Document retention periods and legal holds.
- Review India DPDP Act obligations with qualified legal counsel; do not treat an engineering checklist as legal advice.
- The Blueprint sets an 18+ minimum until a legally reviewed parental-consent flow exists. Confirm age policy and applicable law with counsel before launch.
- A hospital/health module must not be added to the general database; it requires a separate database, threat model, and legal review.

### 11.6 Operational security

- Cloudflare Full (strict), WAF, DDoS controls, Tunnel.
- Private network for database, Redis, and workers.
- Firewall deny-by-default.
- Least-privilege service accounts and storage credentials.
- Encrypted backups and tested restoration.
- Separate production and staging secrets, buckets, and databases.
- No production data copied to development without anonymization and approval.

---

## 12. Media, Feed, Search, and Notifications

### 12.1 Media upload and processing

1. Client asks API for a presigned PUT URL.
2. API validates user permission, file type, size, and upload intent.
3. Presigned URL expires after 10 minutes and constrains content type and maximum size.
4. Browser uploads directly to the private raw R2 bucket.
5. Database stores object key and metadata, not binary data.
6. Worker checks magic bytes, scans where configured, strips EXIF/GPS, re-encodes images, and processes video.
7. Publish validated renditions to the public/private destination according to visibility.
8. Serve through `media.redstarvibe.com` and CDN.
9. Private files use signed GET URLs.
10. Every job is idempotent and retryable; failed work enters a dead-letter path.

Initial limits in Blueprint: images up to 20 MB, reels up to 90 seconds, post videos up to 10 minutes; keep these configurable and validate storage/egress costs.

### 12.2 Feed

- Fan-out-on-write for normal accounts.
- Merge celebrity/high-follower posts at read time.
- Redis for hot timeline entries and buffered counters.
- Flush counters to PostgreSQL on a schedule.
- Use cursor pagination.
- Enforce visibility, block, mute, and follow rules before returning content.
- Have a fallback to Latest if recommendation/embedding services are unavailable.
- Load test high-follower accounts and fan-out backlogs.

### 12.3 Search

- PostgreSQL `tsvector` + GIN for keyword search.
- pgvector for semantic search.
- RRF to merge rankings.
- PostGIS for “near me” business discovery.
- Apply visibility, block, and tenant filters in SQL before content is returned.
- Record embedding model and version; never compare vectors from incompatible models.
- Re-embedding is a background backfill with progress and rollback strategy.

### 12.4 Notifications

Channels: in-app, web push (VAPID), email, SMS, and WhatsApp for booking reminders where approved.

- Check user preferences and quiet hours before delivery.
- Idempotency key: event ID + channel + recipient.
- Retry transient provider errors with backoff.
- Record delivery state and provider response safely.
- Provide opt-out and consent management.
- Do not send marketing messages without appropriate consent.
- Separate transactional booking alerts from marketing notifications.

---

## 13. AI, RAG, and MCP Execution Standards

AI is an optional helper layer, not a dependency for core product operations.

### 13.1 Provider strategy

- `AI_PROVIDER=none`: safe no-AI mode; keyword search remains available.
- `AI_PROVIDER=cloudflare`: default Workers AI for embeddings, vision, speech, and supported small-model tasks.
- `AI_PROVIDER=anthropic`: optional provider for harder reasoning or review workflows.
- Keep provider selection behind an adapter so the application does not depend on one vendor's SDK.
- Add timeouts, bounded retries, circuit breakers, usage accounting, and fallback behavior.

### 13.2 RAG pipeline

1. Select only content eligible for indexing.
2. Remove or redact PII before external processing.
3. Chunk content and store owner/tenant, visibility, source ID, model, and version.
4. Generate embeddings and cache by content hash.
5. Retrieve with permission filters in SQL.
6. Rerank and assemble source-grounded context.
7. Return citations/references where available.
8. Say “I don't know” below the configured confidence threshold.
9. Treat retrieved text as untrusted data; defend against prompt injection.
10. Never index direct messages.
11. Run a golden question set in CI and evaluate quality after model changes.

### 13.3 MCP

- Official MCP Python SDK.
- OAuth 2.1 with PKCE and short-lived scoped tokens.
- Tools call the same service layer as REST; no direct database bypass.
- Read scopes and draft-write scopes are separate.
- Initial tools may include search posts, get profile/stats, read comments, list notifications, get bookings/orders for authorized business users, draft post, and list reported posts for staff.
- Draft-only writes by default; scheduling or publishing requires explicit in-app user approval.
- No destructive tools without a separately reviewed authorization design.
- Rate-limit and audit every tool call.
- Return user-generated content marked as untrusted input.

### 13.4 AI cost controls

- Initial free-plan cap: 50 AI calls/user/day (configurable).
- Cache embeddings by content hash.
- Batch indexing jobs (baseline batch size 32).
- Track usage by user, feature, model, token, and cost.
- Set daily budget alerts and an automatic degraded mode for expensive features.
- Measure cost per active user and per successful task.
- Do not make essential booking, payment, or account flows depend on AI.

---

## 14. Phase-by-Phase Development Execution Roadmap

The roadmap below follows Blueprint v4.0. Phase durations are estimates and assume a focused team. Phases 1–7 total approximately 26 weeks in the baseline plan. Phase 8 is triggered by metrics, not a fixed calendar date. Any additional scope must be estimated and approved rather than silently inserted into a phase.

### Phase 0 — Repository Audit, Product Baseline, and Engineering Setup

**Suggested duration:** 1 week (preparatory; validate actual project state)  
**Goal:** Establish what exists, what works, what is unsafe, and what must be built before changing production.

#### Workstream A: Repository and environment audit

- [ ] Inspect frontend and backend repository structure.
- [ ] Confirm the actual framework/runtime versions against the Blueprint.
- [ ] Inspect `README`, `CLAUDE.md`, `.env.example`, Docker files, Makefile, migrations, CI workflows, and deployment configuration.
- [ ] Run the existing application locally using the documented commands.
- [ ] Run all existing tests, lint, type checks, and builds; record failures without hiding them.
- [ ] Compare existing routes, database tables, workers, and screens with the feature catalog.
- [ ] Verify the current authentication, posts/media, feed, likes/notifications, search, RAG, moderation, MCP, business page, and admin claims individually.
- [ ] Create a feature verification matrix: `working`, `partial`, `broken`, `not implemented`, `unknown`.
- [ ] Identify security-sensitive code and secrets accidentally committed.
- [ ] Inventory dependencies, provider accounts, domains, buckets, and deployment resources.

#### Workstream B: Project governance

- [ ] Create `docs/STATUS.md` with verified feature status.
- [ ] Create `docs/adr/` and record approved architecture decisions.
- [ ] Create issue labels for phase, domain, priority, risk, security, and technical debt.
- [ ] Establish branch, PR, code review, release, and rollback conventions.
- [ ] Establish Definition of Ready/Done and test coverage reporting.
- [ ] Define pilot city and first 2–3 business categories with product owner.

#### Deliverables

- Repository audit report.
- Verified feature matrix.
- Local developer setup guide.
- Initial risk register.
- ADR list for any existing conflicts.
- Prioritized Phase 1 backlog.

#### Exit criteria

- A new developer can run the project using the documented steps.
- Baseline build/test status is known.
- Existing features are verified rather than assumed.
- Critical blockers and security risks are recorded and assigned.

---

### Phase 1 — Production Base and Reliability

**Suggested duration:** 3 weeks  
**Goal:** Make the existing product safe to deploy and operate before adding major new features.

#### Week 1: Authorization, event reliability, and audit

**Backend**
- [ ] Implement the central permission map in `app/core/permissions.py`.
- [ ] Add `require_permission()` dependencies for routes.
- [ ] Add object-level authorization in every service method.
- [ ] Ensure business queries are scoped by `business_id` and user-private queries by owner.
- [ ] Create append-only audit logging for admin/staff actions.
- [ ] Create transactional outbox table and indexes.
- [ ] Update the existing `emit()` interface to write outbox records in the same transaction as domain data.
- [ ] Implement outbox relay with retry, backoff, published state, and dead-letter handling.
- [ ] Add event versioning and idempotent consumer records.
- [ ] Migrate current notification/feed event callers without changing their public service contracts unnecessarily.

**Frontend**
- [ ] Ensure protected pages handle expired sessions safely.
- [ ] Add permission-denied and session-expired states.
- [ ] Remove any UI assumptions that client-side role checks provide security.

**QA**
- [ ] Add cross-user and cross-business authorization tests.
- [ ] Add tests for duplicate event delivery and relay retry.
- [ ] Verify audit events for privileged actions.

#### Week 2: Backups, recovery, monitoring, and staging

**Infrastructure**
- [ ] Create separate staging and production configuration.
- [ ] Create staging database, Redis, and R2 bucket.
- [ ] Protect staging with Cloudflare Access.
- [ ] Configure nightly encrypted PostgreSQL backups to R2 or approved backup storage.
- [ ] Define retention and off-site backup policy.
- [ ] Create restore script and perform a full restore drill.
- [ ] Add health and readiness endpoints.
- [ ] Add database, Redis, worker, queue, and storage health checks.
- [ ] Configure log collection and request IDs.
- [ ] Configure error tracking and uptime checks.
- [ ] Create alerts for failed jobs, queue growth, DB connection exhaustion, disk, memory, and API error rate.

**Operations**
- [ ] Write backup/restore runbook.
- [ ] Write service restart and incident escalation runbook.
- [ ] Confirm who receives production alerts and how acknowledgement works.

#### Week 3: CI/CD and deployment safety

**CI**
- [ ] Build frontend and backend in GitHub Actions.
- [ ] Run format, lint, type checks, unit/integration tests, dependency scans, and container scans.
- [ ] Build Docker images and publish to GHCR.
- [ ] Generate/check OpenAPI and API types.
- [ ] Add migration validation.
- [ ] Add staging deploy workflow.
- [ ] Add production deploy approval gate.
- [ ] Use immutable image tags and record deployed commit SHA.

**Deployment**
- [ ] Configure Nginx as the only public app entry.
- [ ] Configure Cloudflare Full (strict) and Tunnel.
- [ ] Ensure Postgres, Redis, workers, and internal ports are not publicly exposed.
- [ ] Run Alembic migrations as a one-shot pre-deploy step.
- [ ] Add health-gated deployment and rollback procedure.
- [ ] Verify staging deployment from a clean commit.

#### Phase 1 deliverables

- Permission map and object-level authorization.
- Transactional outbox and idempotent event consumers.
- Append-only audit log.
- Encrypted backup and tested restore.
- Staging environment.
- CI/CD with staging deploy and production approval.
- Monitoring, alerting, and operational runbooks.

#### Phase 1 exit criteria

- Restore drill passes and RPO/RTO are measured.
- Staging deployment is automated.
- Alerts reach the responsible team and are acknowledged in a test.
- Critical authorization tests pass.
- Outbox event loss scenario is tested.
- No critical/high security finding remains unowned.
- Production release and rollback are documented.

---

### Phase 2 — Business Daily Tool

**Suggested duration:** 4 weeks  
**Goal:** Make RedStarVibe useful every day to local service businesses and customers.

#### Week 1: Business profile, services, and hours

- [ ] Finalize business categories and onboarding flow for the pilot trades.
- [ ] Create/verify business profile fields: name, slug, description, category, contact, address, location, service area, photos, opening status.
- [ ] Implement reserved username/slug rules and uniqueness.
- [ ] Implement business page editing and public SSR page.
- [ ] Add Open Graph metadata for business pages.
- [ ] Implement services with name, description, price/rate, duration, status, and optional variants.
- [ ] Implement business hours, holidays, exceptions, and timezone handling.
- [ ] Add staff/resources that can be booked.
- [ ] Add business owner and staff permissions.
- [ ] Add validation and audit events for sensitive business edits.

#### Week 2: Availability and booking core

- [ ] Design booking state machine and cancellation rules.
- [ ] Create availability/resource model.
- [ ] Implement slot calculation from service duration, working hours, buffers, holidays, and existing bookings.
- [ ] Add PostgreSQL exclusion constraint using `btree_gist` to prevent overlapping active bookings.
- [ ] Implement booking create/read/update/cancel APIs.
- [ ] Require idempotency key for booking creation.
- [ ] Enforce customer, business, and staff authorization.
- [ ] Prevent booking outside business hours or outside the service area where relevant.
- [ ] Add booking history and status transitions.
- [ ] Add concurrency tests for double booking.

#### Week 3: Calendar, reminders, reviews, and inbox

- [ ] Build business calendar with day/week views.
- [ ] Build customer booking list and detail.
- [ ] Add booking confirmation and cancellation notifications.
- [ ] Add reminder scheduling using Celery beat and outbox events.
- [ ] Add customer review submission after eligible completed bookings.
- [ ] Add business review replies with moderation/abuse controls.
- [ ] Add quotation/enquiry request workflow where relevant.
- [ ] Add a basic business inbox linking a conversation/enquiry to a customer and booking.
- [ ] Add quiet hours, notification preferences, and idempotent delivery.

#### Week 4: Local discovery and pilot validation

- [ ] Add PostGIS geography field and GiST index.
- [ ] Implement nearby business search with distance and category filters.
- [ ] Apply visibility, active status, and moderation filters.
- [ ] Add map/list UX only if product requirements and location permissions support it.
- [ ] Add basic business analytics: profile views, enquiries, booking count, conversion.
- [ ] Onboard first pilot businesses and observe actual use.
- [ ] Fix onboarding friction, timezone errors, calendar conflicts, and notification failures.

#### Phase 2 deliverables

- Business profile and public page.
- Services, business hours, staff/resources.
- Booking APIs and customer/business calendar.
- Double-booking prevention.
- Reminders, reviews/replies, quotation request, business inbox.
- Nearby search.
- Pilot onboarding and support guide.

#### Phase 2 exit criteria

- At least 20 businesses take real bookings for 2 weeks.
- No unresolved double-booking defect.
- Booking creation, cancellation, reminder, and review flows pass end-to-end tests.
- Business owners can manage services and hours without developer help.
- Booking success/failure and reminder delivery are measurable.

---

### Phase 3 — Viral Growth: Cards, Albums, Slideshows, and Referrals

**Suggested duration:** 3 weeks  
**Goal:** Create useful, shareable content that brings new visitors and business discovery.

#### Week 1: Templates and digital cards

- [ ] Define template schema and supported output dimensions.
- [ ] Create birthday, wedding, festival, business promotion, and greeting templates.
- [ ] Support editable text, images, colors, and safe typography.
- [ ] Use licensed fonts, including licensed Hindi/Indian language fonts.
- [ ] Create browser preview and server render path.
- [ ] Add watermark policy for free/premium tiers, if monetization rules are approved.
- [ ] Validate user-uploaded images and sanitize text.
- [ ] Store rendered output in R2; database stores object keys and metadata.
- [ ] Make render jobs idempotent using an input hash.
- [ ] Add moderation and report capability for shared public content.

#### Week 2: Albums and slideshow

- [ ] Implement album creation, page order, cover, visibility, and share settings.
- [ ] Build responsive flipbook/page-turn experience.
- [ ] Add image optimization and lazy loading.
- [ ] Build slideshow preview in the browser.
- [ ] Generate downloadable MP4 through FFmpeg worker only when user requests export/share.
- [ ] Add progress status, retry, cancellation, and job cleanup.
- [ ] Use only royalty-free or properly licensed music; do not include unlicensed film songs.
- [ ] Add size/duration limits and storage quotas.

#### Week 3: Referrals and share loop

- [ ] Create referral/invite links with attribution.
- [ ] Add QR code generation for business pages and cards.
- [ ] Add Open Graph share pages and WhatsApp-friendly previews.
- [ ] Track share creation, click, landing, signup, and activation events with privacy-aware analytics.
- [ ] Add fraud checks for self-referrals, duplicate accounts, and suspicious reward patterns.
- [ ] Add Star Points only after reward policy, abuse controls, and financial implications are approved.
- [ ] Pilot templates with real users and measure repeat sharing.

#### Phase 3 deliverables

- Card templates and rendering worker.
- Albums and slideshow creation/export.
- Referral links, QR codes, and share previews.
- Usage analytics and abuse controls.

#### Phase 3 exit criteria

- 10% of active users share at least one card per week.
- Share previews work across supported messaging/social clients.
- Render failures and processing times are monitored.
- No unlicensed media assets are used.
- Storage and worker costs per render are understood.

---

### Phase 4 — Social Complete

**Suggested duration:** 5 weeks  
**Goal:** Complete the core social interaction layer while protecting user safety and privacy.

#### Week 1: Comments and social graph controls

- [ ] Implement threaded comments and replies.
- [ ] Add edit/delete rules and moderation state.
- [ ] Add follow requests for private accounts.
- [ ] Implement block, mute, and restrict semantics.
- [ ] Ensure blocked users cannot bypass controls through search, feed, comments, or chat.
- [ ] Add mentions and notification events.
- [ ] Add hashtag pages and safe indexing.
- [ ] Add save/bookmark and collections.

#### Week 2: Stories and highlights

- [ ] Implement 24-hour story expiry and cleanup.
- [ ] Support image/video story upload through the media pipeline.
- [ ] Add story viewers and privacy controls.
- [ ] Add highlights that preserve selected stories.
- [ ] Add reporting and moderation workflow.
- [ ] Add story view counters with buffered writes.

#### Week 3: Direct messages

- [ ] Create conversations, members, messages, receipts, and attachment metadata.
- [ ] Implement WebSocket typed frames and heartbeat every 25 seconds.
- [ ] Persist messages before delivery.
- [ ] Use Redis pub/sub to route events across WebSocket process replicas.
- [ ] Implement message sequence numbers and reconnect catch-up from last acknowledged sequence.
- [ ] Add unread counts, read receipts, typing indicators, and online presence.
- [ ] Add web push for offline users.
- [ ] Enforce block, privacy, membership, rate limits, and report controls.
- [ ] Ensure direct messages are never indexed for AI/RAG.

#### Week 4: Group chat and voice notes

- [ ] Add group conversation creation and member roles.
- [ ] Add invite/remove/leave controls and group limits.
- [ ] Add voice note upload and playback using private media rules.
- [ ] Add abuse reporting, mute, and notification settings.
- [ ] Add message retention and deletion policy.
- [ ] Load test connection counts and message throughput.

#### Week 5: Reels and social retention

- [ ] Implement reel publishing and playback on the existing HLS media pipeline.
- [ ] Add duration and file constraints.
- [ ] Add feed integration and moderation.
- [ ] Tune feed fan-out and high-follower merge behavior.
- [ ] Add retention analytics and cohort dashboards.
- [ ] Run usability and safety review before broad rollout.

#### Phase 4 deliverables

- Comments, follows, mentions, hashtags, saves, collections.
- Block/mute/restrict and private follow requests.
- Stories and highlights.
- One-to-one and group DMs, voice notes, receipts, reconnect recovery.
- Reels and retention measurement.

#### Phase 4 exit criteria

- Day-7 retention is measured and improving against the agreed baseline.
- Chat reconnect does not lose persisted messages.
- Block/privacy controls pass end-to-end tests across all discovery surfaces.
- Moderation and reporting workflows are staffed and operational.
- WebSocket capacity and queue lag are measured.

---

### Phase 5 — Events and Shop

**Suggested duration:** 4 weeks  
**Goal:** Expand business utility to event packages and local product commerce.

#### Week 1: Event organizer and packages

- [ ] Create organizer account/profile and permissions.
- [ ] Define event types, package categories, and package item structure.
- [ ] Implement packages with price, inclusions, exclusions, capacity, and availability.
- [ ] Add package images and public share page.
- [ ] Add quote/enquiry workflow.
- [ ] Add event booking lifecycle and cancellation rules.

#### Week 2: Vendor network and availability

- [ ] Implement vendor profiles and categories.
- [ ] Implement vendor invitations and acceptance/decline.
- [ ] Reuse booking availability principles to prevent overlapping vendor commitments.
- [ ] Add package assembly from vendor services.
- [ ] Add organizer/vendor/customer communication.
- [ ] Add event timeline and status history.
- [ ] Add audit trail for package and vendor changes.

#### Week 3: Shop catalog and inventory

- [ ] Implement shop profile and product catalog.
- [ ] Add product variants, SKU, price, photos, description, availability, and stock.
- [ ] Add category and search filters.
- [ ] Add inventory reservation and atomic stock update.
- [ ] Add product moderation and seller policies.
- [ ] Add customer cart/checkout preparation without taking payment until Phase 6.
- [ ] Define shipping, pickup, delivery, returns, and cancellation policies before enabling orders.

#### Week 4: Orders and pilot

- [ ] Implement order, order items, and order status history.
- [ ] Implement seller order dashboard.
- [ ] Add order notifications and idempotency.
- [ ] Add bulk order with date where needed.
- [ ] Add refund/cancel/stock-restoration state handling.
- [ ] Onboard pilot event companies and shops.
- [ ] Measure order completion, vendor response, and support load.

#### Phase 5 deliverables

- Event organizer profiles, packages, vendor invites, vendor availability, event bookings.
- Shop profiles, products, inventory, orders, order status.
- Seller/organizer dashboards and customer notifications.
- Operational policies for returns, cancellation, delivery, and vendor disputes.

#### Phase 5 exit criteria

- At least 5 event companies and 10 shops are live.
- No inventory overselling under concurrency tests.
- Vendor availability and event booking conflicts are prevented.
- Order status and cancellation flows are understandable to users.
- Support processes exist for disputes and failed fulfilment.

---

### Phase 6 — Money: Payments, Plans, Promotion, and Payouts

**Suggested duration:** 3 weeks  
**Goal:** Introduce secure, reconciled monetization only after the transaction flows are stable.

#### Week 1: Payment foundation

- [ ] Confirm business model, fees, refund rules, settlement timing, GST treatment, and provider account eligibility.
- [ ] Integrate Razorpay using server-created orders.
- [ ] Calculate amount on the server from trusted database records; never trust client amount.
- [ ] Store amounts as integer paise.
- [ ] Verify webhook HMAC signatures.
- [ ] Store provider event ID with a unique constraint.
- [ ] Only verified webhook events can mark a payment paid.
- [ ] Make webhook handling idempotent.
- [ ] Add payment status state machine: created, pending, paid, failed, refunded, partially refunded as applicable.
- [ ] Add payment reconciliation job every 15 minutes for pending payments.
- [ ] Add sandbox and failure-path tests.

#### Week 2: Deposits, plans, and invoices

- [ ] Add booking advance deposits.
- [ ] Define payment deadline, expiry, cancellation, and refund behavior.
- [ ] Implement subscription plans and entitlement checks.
- [ ] Add plan upgrade/downgrade/cancel lifecycle.
- [ ] Generate GST invoices only after accountant/legal review of invoice requirements.
- [ ] Add customer payment history and business payout visibility.
- [ ] Add payment support/admin tools with audit logging.

#### Week 3: Promotion and payout controls

- [ ] Add boosted posts/local promotion only after ad policy and moderation review.
- [ ] Add daily budget and category/geo targeting safeguards.
- [ ] Add creator tips only after payout, tax, and abuse policy is approved.
- [ ] Integrate Razorpay Route or the approved payout provider after eligibility review.
- [ ] Add payout ledger, reconciliation, failed payout handling, and audit.
- [ ] Add payment incident runbook and provider outage handling.
- [ ] Conduct end-to-end test from booking/order to webhook, ledger, invoice, refund, and payout.

#### Phase 6 deliverables

- Razorpay payment integration.
- Advance deposits.
- Plans/subscriptions and entitlement checks.
- Approved invoices.
- Promotion/boost capability where policy allows.
- Payout and reconciliation workflows.

#### Phase 6 exit criteria

- First paid plan completes successfully.
- First advance payment completes and reconciles.
- Duplicate webhooks do not duplicate payments or entitlements.
- Refund and failed-payment scenarios are tested.
- Financial ledger reconciles with provider records.
- Legal/accounting review is complete for enabled monetization.

---

### Phase 7 — Calls and AI Plus

**Suggested duration:** 4 weeks  
**Goal:** Add real-time calling and advanced AI features while maintaining privacy and cost controls.

#### Week 1: LiveKit foundation

- [ ] Create LiveKit environment and provider configuration.
- [ ] Generate short-lived room tokens server-side (baseline token lifetime: 5 minutes).
- [ ] Check block, privacy, conversation membership, and call permissions before issuing tokens.
- [ ] Implement one-to-one audio/video calling.
- [ ] Add call lifecycle: ringing, accepted, declined, missed, ended.
- [ ] Add call notifications and call history.
- [ ] Add reconnect and network-failure UX.
- [ ] Add user controls for microphone/camera and device permissions.

#### Week 2: Group calls and reliability

- [ ] Implement group calls with participant limits.
- [ ] Add room authorization and participant removal.
- [ ] Add call quality telemetry and provider error handling.
- [ ] Test mobile network changes, backgrounding, permission denial, and reconnect.
- [ ] Define abuse reporting and call safety policy.
- [ ] Load test expected concurrency and verify provider cost.

#### Week 3: AI content assistance

- [ ] Add AI caption and hashtag suggestions.
- [ ] Add image alt text suggestions.
- [ ] Add business listing and product description assistance.
- [ ] Add AI moderation warning and spam detection.
- [ ] Require user review before publishing AI-generated text.
- [ ] Track provider, model, usage, latency, and cost.
- [ ] Add provider fallback and AI-off behavior.

#### Week 4: Subtitles, translation, and business assistant

- [ ] Add Whisper-based subtitles through Workers AI or approved provider.
- [ ] Add translation for supported Indian languages.
- [ ] Add toxic-comment warning with human moderation for consequential actions.
- [ ] Add business assistant queries such as upcoming bookings and orders through authorized MCP/RAG tools.
- [ ] Ensure every response is tenant-scoped and source-grounded.
- [ ] Add golden test set and evaluation report.
- [ ] Review AI cost per active user and adjust quotas.

#### Phase 7 deliverables

- LiveKit one-to-one and group calling.
- Captions, hashtags, alt text, subtitles, translation.
- Toxic comment warning and spam detection.
- Business assistant using permission-checked services.
- AI quality, usage, and cost dashboards.

#### Phase 7 exit criteria

- Call flows work on supported devices and network conditions.
- Unauthorized users cannot join calls or access business data.
- AI cost per active user is below the approved budget.
- AI features degrade safely when providers fail.
- RAG answers respect tenant filters and cite sources where available.
- Users can review/edit AI-generated content before publication.

---

### Phase 8 — Scale, Resilience, and Platform Evolution

**Duration:** Triggered by measured demand; no fixed start date  
**Goal:** Scale bottlenecked components without rewriting the platform prematurely.

#### Scale readiness assessment

- [ ] Review p95/p99 latency and error rates by endpoint.
- [ ] Review CPU, memory, disk I/O, network, and database connection utilization.
- [ ] Review slow queries, lock waits, table/index growth, and cache hit rate.
- [ ] Review queue depth, oldest job age, retry rate, and worker saturation.
- [ ] Review WebSocket concurrency and message delivery latency.
- [ ] Review media storage, egress, transcode time, and CDN cache hit ratio.
- [ ] Review per-user and total AI spend.
- [ ] Identify the dominant bottleneck and test one scaling change at a time.

#### Scaling ladder

**Level 1 — Optimize the existing deployment**
- Fix N+1 queries and missing indexes.
- Add query plans and connection pool tuning.
- Cache read-heavy data with explicit invalidation/TTL.
- Tune worker concurrency and queue routing.
- Optimize media renditions and CDN caching.
- Add request/response compression where useful.
- Remove memory leaks and unbounded in-memory state.

**Level 2 — Add replicas**
- Add stateless API replicas behind the gateway/load balancer.
- Add Next.js web replicas as needed.
- Add separate WebSocket replicas with Redis pub/sub.
- Add separate Celery pools for default, media, and AI queues.
- Keep one active Celery beat scheduler or use a safe leader mechanism.
- Add PgBouncer and tune connection limits.
- Add Redis HA/cluster only when the workload and operations justify it.

**Level 3 — Database scale**
- Add read replicas for read-heavy workloads.
- Move eligible reads to replicas with documented consistency expectations.
- Partition messages, notifications, and analytics by month when table size/query patterns justify it.
- Hash partition likes by post ID only with a reviewed design and migration plan.
- Consider archival and retention for old events/media metadata.
- Consider dedicated search infrastructure only when PostgreSQL hybrid search no longer meets measured needs.

**Level 4 — Isolate hot domains**
- Consider extracting chat, feed, or media processing only if independent scaling/release/security needs are proven.
- Define service ownership, API/event contracts, data ownership, tracing, deployment, and failure modes before extraction.
- Do not split services solely to follow a microservices trend.

**Level 5 — Orchestration and streaming**
- Introduce Kubernetes only when multi-node scheduling, deployment automation, service discovery, and team operations justify its complexity.
- Introduce Kafka only when event throughput, replay, consumer independence, or queue semantics exceed the Celery/Redis design.
- Add multi-region architecture only after data residency, latency, consistency, and operational costs are reviewed.

#### Phase 8 exit criteria

- Capacity tests meet agreed targets with operational headroom.
- Scaling changes have measurable benefit.
- Failure of one app replica does not cause data loss.
- Backup/restore and disaster recovery remain tested after topology changes.
- On-call runbooks and dashboards are updated.

---

## 15. Additional Product Backlog and Placement

The Production Blueprint includes additional business, event, wellbeing, growth, and community ideas. These are not all launch blockers. Prioritize them only after the core phases have evidence of adoption and the team has capacity.

### 15.1 Business growth modules

Potential modules include:

- Quick Shop and seller onboarding improvements.
- Reusable business templates.
- AI-assisted product/service listing.
- Seller coach and business insights.
- Packages and vendor network.
- Unified business calendar.
- Business albums and promotional content.

### 15.2 Event modules

- Event packages and package comparison.
- Vendor availability and invitations.
- Multi-vendor quote assembly.
- Event schedule and coordination.
- Event booking and payment milestones.

### 15.3 Wellbeing and community modules

Ideas in the source blueprint include challenges, memories, calm corner, micro-courses, kindness wall, and wellbeing safety. These require a separate product brief, safety assessment, moderation model, and success metrics before implementation. Do not imply that these are medical or mental-health services.

### 15.4 Later modules

- School module.
- Hospital module (separate database and legal review required).
- Live streaming.
- Larger communities.

These remain P8+ backlog candidates, not committed launch scope.

### 15.5 Star Points and rewards

If implemented:

- Define transparent earning rules and redemption value.
- Prevent self-referrals, fake accounts, scripted activity, and collusion.
- Maintain an auditable points ledger.
- Apply rate limits and manual review for suspicious activity.
- Do not let points create unapproved cash-equivalent or financial obligations.

---

## 16. Admin, Moderation, Support, and Operations

### 16.1 Role model

Keep role names simple and permissions explicit:

- `user`
- `business`
- `staff`
- `admin`
- `superadmin`

The permission map is authoritative. Business staff permissions are additionally scoped to a business. Do not grant broad admin privileges to support staff.

### 16.2 Admin dashboard capabilities

- User and business lookup with access logging.
- Report and moderation queues.
- Review and resolve reported content.
- Business verification workflow.
- Support tickets and escalation.
- Payment/payout support views with sensitive data masked.
- Operational status: API health, queue lag, worker errors, webhook failures.
- Audit log search.
- Feature flag and configuration changes with approvals.

### 16.3 Moderation workflow

- Users can report posts, comments, profiles, businesses, and messages.
- Define severity, category, evidence, status, reviewer, and resolution.
- Provide appeal/escalation where appropriate.
- Preserve evidence according to retention policy.
- Apply human review for high-impact decisions.
- AI moderation can prioritize or warn, but must not silently replace policy and appeal processes.
- Measure report response time, false positives, repeat abuse, and moderator workload.

### 16.4 Support operations

- Publish help and contact channels.
- Define ticket categories, priority, response target, escalation owner, and closure reasons.
- Build internal runbooks for account recovery, booking disputes, payment issues, media failures, and moderation appeals.
- Never ask support agents to collect passwords or OTPs.

---

## 17. DevOps, Environments, CI/CD, and Release Management

### 17.1 Environments

**Local**
- Docker Compose.
- PostgreSQL and Redis.
- Local object storage emulator only if it accurately reflects required R2 behavior.
- Seeded synthetic data.
- No production secrets or real user data.

**Staging**
- Separate database, Redis, R2 bucket, and provider credentials.
- Protected by Cloudflare Access.
- Production-like configuration and migration path.
- Synthetic or anonymized data only.

**Production**
- Cloudflare edge + Tunnel + Nginx.
- Private application/data network.
- Encrypted backups.
- Monitoring, alerting, incident owner.
- Restricted administrative access and MFA.

### 17.2 CI pipeline

For every pull request:

1. Install pinned dependencies.
2. Format and lint frontend/backend.
3. Run TypeScript and Python type checks.
4. Run unit tests.
5. Run database integration tests.
6. Run API contract/OpenAPI checks.
7. Run authorization and security tests.
8. Run dependency and container vulnerability scans.
9. Build frontend/backend images.
10. Validate migrations.
11. Publish test and coverage reports.

Coverage target: at least 60% overall as an initial gate, with a target of 80%+ for critical business services. Coverage percentage alone is not proof of quality; test important behavior and failure cases.

### 17.3 Deployment sequence

1. Build immutable image.
2. Run pre-deploy checks.
3. Back up if the migration risk requires it.
4. Run expand-only migration.
5. Deploy new application version.
6. Wait for health/readiness.
7. Run smoke tests.
8. Observe metrics and errors.
9. Complete contract migration in a later release after old code no longer needs old schema.
10. Roll back application image if needed; use forward-fix for irreversible data migrations.

### 17.4 Release controls

- Feature flags for incomplete or risky capabilities.
- Canary or staged rollout where possible.
- Release notes and migration notes.
- Named release owner.
- Production change log.
- Rollback criteria.
- Post-release verification checklist.
- No Friday/holiday high-risk migrations without explicit operational coverage.

---

## 18. Observability, SLOs, and Scaling Triggers

### 18.1 Required telemetry

- Structured logs with request ID, trace ID, user/business identifier only where privacy policy allows, and module name.
- Distributed traces across gateway, API, database, queue, and provider calls.
- Metrics for request rate, latency, error rate, saturation, queue age, job retries, DB pool, Redis, WebSockets, media, and AI cost.
- Dashboards by product flow, not only by server.
- Alerts with actionable runbooks and severity.

### 18.2 Initial SLO dashboard

Track at minimum:

- API p50/p95/p99 latency and 4xx/5xx rate.
- Login and signup success rate.
- Post upload success and processing time.
- Feed latency and empty/error rate.
- Booking create success, conflict rate, and reminder delivery.
- Message delivery latency and reconnect recovery.
- Payment webhook processing and reconciliation lag.
- Queue oldest-job age and dead-letter count.
- Database connection utilization and slow queries.
- Storage usage, CDN hit ratio, and media processing failure.
- AI requests, latency, provider failure, and cost per active user.

### 18.3 Scaling triggers

Use measured evidence, not a single CPU spike. Review scaling when one or more of these persist through representative peak periods:

- API p95 exceeds its SLO after query/code optimization.
- CPU or memory remains above the agreed safe operating range.
- Database connections approach the configured pool limit.
- Queue age exceeds the business SLA or grows continuously.
- WebSocket connection capacity or delivery latency breaches SLO.
- Read workload causes primary database contention.
- Media processing backlog causes user-visible delays.
- Storage/egress costs exceed the approved unit economics.
- AI spend exceeds budget despite quotas and caching.

For each trigger, write a short capacity report: observed metric, time window, root cause, options, cost, expected gain, rollback, and owner.

---

## 19. Hosting and Cost Management

### 19.1 Launch-stage baseline

The Blueprint proposes a low-cost launch using Cloudflare services, a single VM, Docker, PostgreSQL, Redis, R2, GitHub Actions, and open-source observability where practical.

Potential baseline components:

- Cloudflare DNS, TLS, WAF, DDoS, Turnstile, Tunnel, and CDN.
- One appropriately sized VM for initial app processes.
- Docker Compose for process management at the first stage.
- PostgreSQL and Redis on private network or managed services where reliability requires it.
- R2 for media.
- GHCR and GitHub Actions.
- Sentry / Grafana / Prometheus / Loki / Uptime Kuma according to operational capacity.

**Important:** Free tiers change, have quotas, and are not a production availability guarantee. Confirm current provider limits, data retention, backups, bandwidth, and support before relying on a free plan. Do not place critical production data on a free service without tested export and recovery.

### 19.2 Cost controls

- Track infrastructure cost per active user, booking, order, media GB, and AI task.
- Set budget alerts and owner.
- Use media compression, lifecycle policies, and CDN caching.
- Set upload quotas and fair-use limits.
- Cache embeddings and avoid duplicate AI calls.
- Run expensive AI and video work asynchronously.
- Use worker concurrency caps.
- Review provider invoices monthly.
- Keep a provider replacement plan for critical dependencies.

### 19.3 Monetization sequence

The Blueprint's intended progression:

1. Free launch: validate core usage and business retention.
2. Business plan: consider when 50+ businesses have 10+ bookings/week; paid benefits may include reminders, deposits, analytics, more services, and watermark removal.
3. Promotion: consider when the city has 1,000+ weekly active customers; boosted posts and local promotion need moderation and daily caps.
4. Premium/Creator: when users and creators demonstrate demand for badges, templates, tips, or subscriber posts.
5. Enterprise: when event companies need staff accounts, vendor network, and support.

Validate willingness to pay before building complex billing features.

---

## 20. Testing Strategy

### 20.1 Test pyramid

**Unit tests**
- Service rules, validators, permission functions, state machines, formatting, pricing, and utility logic.

**Integration tests**
- Database transactions, repositories, migrations, outbox, Redis, Celery tasks, R2 adapter, webhooks, and provider adapters.

**Contract tests**
- OpenAPI schemas, generated TypeScript types, event payload versions, MCP tool schemas.

**End-to-end tests**
- Signup/login, create post, upload media, business setup, service creation, booking, cancellation, reminders, card sharing, DM, order, payment, moderation, account deletion.

**Load and resilience tests**
- Feed reads, booking concurrency, message delivery, upload initiation, worker backlog, payment webhook bursts, AI provider timeouts, replica loss, Redis/database failover where supported.

**Security tests**
- IDOR/BOLA, CSRF, XSS, SSRF, injection, rate-limit bypass, upload spoofing, privilege escalation, session fixation/reuse, tenant isolation, webhook forgery.

### 20.2 Critical scenario matrix

| Area | Must-test scenarios |
|---|---|
| Authentication | expired access token, refresh rotation, reuse detection, MFA, account recovery |
| Authorization | cross-user access, cross-business staff access, admin scope |
| Booking | same slot race, timezone/DST, holiday, cancellation, retry/idempotency |
| Media | spoofed MIME, oversized file, malware, private asset access, failed transcode |
| Feed | block/mute, private profile, celebrity merge, fan-out retry |
| Chat | reconnect, duplicate event, offline delivery, blocked user, group membership |
| Shop | concurrent inventory decrement, order cancellation, stock restoration |
| Payments | invalid signature, duplicate webhook, delayed webhook, refund, reconciliation |
| AI | provider unavailable, prompt injection, tenant boundary, wrong model vector, budget exceeded |
| Privacy | export, deletion, consent withdrawal, retention purge |

### 20.3 Test data

- Use synthetic users, businesses, bookings, products, posts, and media.
- Include multiple tenants and roles in every integration suite.
- Never rely on a single admin test account.
- Keep reproducible seed scripts and deterministic fixtures.
- Avoid real personal information in screenshots, test logs, and demo datasets.

---

## 21. Data Migration, Backup, and Disaster Recovery

### 21.1 Backup plan

- Encrypted nightly PostgreSQL backups.
- Point-in-time recovery/WAL archiving where supported by the selected database deployment.
- Separate backup credentials and storage location.
- Retention policy with daily/weekly/monthly tiers.
- R2 object versioning or an equivalent recovery strategy for critical media where cost and provider support allow.
- Backup success monitoring and alerting.
- Quarterly restore drill at minimum; more often before major changes.

### 21.2 Restore drill checklist

- [ ] Select a known backup and record its timestamp.
- [ ] Restore into an isolated environment.
- [ ] Restore required WAL/PITR range if configured.
- [ ] Verify schema and migration state.
- [ ] Verify user/business/post/booking/order counts.
- [ ] Verify referential and tenant integrity.
- [ ] Verify media object references and sample files.
- [ ] Run application smoke tests.
- [ ] Measure recovery time and data loss window.
- [ ] Record issues and remediate.
- [ ] Do not overwrite production during a drill.

### 21.3 Account and data lifecycle

- Define account deactivation vs deletion.
- Define soft-delete period and hard-purge schedule.
- Include media, search embeddings, caches, exports, and provider-held data in deletion design.
- Honor legal holds where required.
- Log deletion jobs without retaining unnecessary personal data.
- Provide user-facing status for export/deletion requests.

---

## 22. Documentation Deliverables

Maintain these documents as implementation progresses:

| Document | Required content |
|---|---|
| `README.md` | project overview, prerequisites, local setup, common commands |
| `docs/STATUS.md` | verified feature status and current phase |
| `docs/adr/` | architecture decisions, trade-offs, date, status |
| `docs/architecture.md` | component diagram, module ownership, data flows |
| `docs/api/` | API conventions, generated OpenAPI, auth and pagination |
| `docs/database.md` | schema ownership, migration policy, indexes, retention |
| `docs/security/` | threat model, privacy controls, incident contacts |
| `docs/runbooks/deploy.md` | deploy, smoke test, rollback |
| `docs/runbooks/backup-restore.md` | backup verification and restore steps |
| `docs/runbooks/incident-response.md` | triage, severity, escalation, communication |
| `docs/runbooks/provider-outage.md` | AI, payment, media, email/SMS provider fallback |
| `docs/testing.md` | test layers, local commands, CI expectations |
| `docs/operations-costs.md` | budgets, quotas, cost per user/workflow |
| `docs/product/` | personas, user journeys, policies, pilot feedback |

---

## 23. First 14-Day Execution Checklist

This sequence follows the Production Blueprint's initial two-week priorities. Adjust only after repository audit.

| Days | Work | Expected output |
|---|---|---|
| 1–2 | Run `bootstrap_env.py`, `make up`, `make seed` if present; verify gateway routes; inspect repo; write conflict ADRs | Reproducible local setup and architecture decisions |
| 3–4 | Outbox table + relay; migrate `emit()` callers; permission map + `require_permission()` | Reliable events and centralized permissions |
| 5–6 | Nightly encrypted backup to R2; restore drill script; health/readiness endpoints | Tested recovery and health checks |
| 7–8 | Staging VM/environment, GitHub environments, image build and deploy workflow | Automated staging deployment |
| 9–10 | Business services/hours; OG tags for public profile; reserved usernames | Business profile foundation |
| 11–12 | Booking module with exclusion constraint, slots API, calendar UI | Safe booking foundation |
| 13–14 | Reminder worker; onboard first real businesses; test WhatsApp sharing | First real-world validation |

If the repository does not contain a command listed above, do not invent a replacement silently. Inspect the current Makefile/scripts and document the equivalent command.

---

## 24. Risk Register

| Risk | Impact | Mitigation / owner |
|---|---|---|
| Building features before validating demand | High wasted effort | Pilot 20–30 businesses; product owner |
| Existing code differs from docs | Wrong migrations or duplicated work | Phase 0 audit and ADRs; tech lead |
| Broken tenant isolation | Severe privacy/security incident | SQL tenant filters, service checks, cross-tenant tests; backend/security |
| Lost async events | Missing notifications/feed work | Transactional outbox, idempotent consumers; backend |
| Double bookings | Business/customer trust loss | DB exclusion constraint and concurrency tests; booking owner |
| Payment mismatch or duplicate charge | Financial and legal impact | Signed webhooks, unique event IDs, idempotency, reconciliation; payments owner |
| Media abuse or malware | User safety and infrastructure risk | Presigned limits, magic bytes, scanning, re-encoding, quotas; media/security |
| AI hallucination or data leakage | Trust/privacy incident | SQL permission filters, source citations, PII redaction, human review; AI/security |
| Provider outage | Feature interruption | Timeouts, circuit breakers, fallback/degraded modes; SRE |
| Free-tier limits change | Unexpected cost/outage | Budget monitoring, export plan, paid fallback; operations |
| Premature microservices/Kubernetes | Complexity and slower delivery | Modular monolith until metrics justify extraction; tech lead |
| Weak moderation coverage | User harm and platform abuse | Staffing, escalation, policy, audit and appeals; trust & safety |
| Regulatory uncertainty | Launch delay or liability | Legal/accounting review before age, payments, health, and data-sensitive features; product/legal |
| Team capacity underestimated | Schedule slippage | Phase gates, explicit estimates, scope control; product owner |

---

## 25. Release Readiness Checklist

Before each public release:

### Product
- [ ] User journey and acceptance criteria pass.
- [ ] Feature flag and rollout plan are configured.
- [ ] Help/support content is updated.
- [ ] Known limitations are communicated.

### Engineering
- [ ] CI is green.
- [ ] Critical unit/integration/e2e tests pass.
- [ ] OpenAPI and generated types are current.
- [ ] Migrations reviewed and staging-tested.
- [ ] Performance budget checked.
- [ ] No critical/high security issue is unresolved without approved exception.

### Operations
- [ ] Backup is recent and verified.
- [ ] Dashboards and alerts are active.
- [ ] On-call/incident owner is assigned.
- [ ] Deploy and rollback steps are ready.
- [ ] Provider quotas and billing are checked.

### Trust and compliance
- [ ] Privacy, consent, and retention implications reviewed.
- [ ] Moderation/support coverage is ready.
- [ ] Terms/policies updated where required.
- [ ] Payment and legal checks completed for money-related releases.

---

## 26. Project Status Template

Copy this section into `docs/STATUS.md` and update it continuously.

```markdown
# RedStarVibe Project Status

Updated: YYYY-MM-DD
Current phase: Phase 0 / Phase 1 / ...
Release: ...

## Phase status
- [ ] Phase 0 — Repository audit
- [ ] Phase 1 — Production base
- [ ] Phase 2 — Business daily tool
- [ ] Phase 3 — Viral growth
- [ ] Phase 4 — Social complete
- [ ] Phase 5 — Events and shop
- [ ] Phase 6 — Money
- [ ] Phase 7 — Calls and AI plus
- [ ] Phase 8 — Scale (metrics-triggered)

## Verified existing features
| Feature | Status | Evidence / test | Owner |
|---|---|---|---|
| Authentication | Unknown | | |
| Posts/media | Unknown | | |
| Feed | Unknown | | |
| Likes/notifications | Unknown | | |
| Search | Unknown | | |
| RAG assistant | Unknown | | |
| Image moderation | Unknown | | |
| MCP | Unknown | | |
| Business page | Unknown | | |
| Admin panel | Unknown | | |

## Current blockers
- ...

## Risks
- ...

## Production metrics
- API p95:
- Error rate:
- Queue oldest-job age:
- DB connection utilization:
- Backup last success:
- Restore last tested:
- AI cost / active user:
```

---

## 27. Final Implementation Rules

1. Build the reliable foundation before adding more feature surface area.
2. Verify the existing code before rewriting or declaring a feature complete.
3. Keep the modular monolith and domain boundaries intact.
4. Make database constraints enforce critical invariants such as booking overlap and inventory.
5. Make asynchronous work reliable through the transactional outbox and idempotent consumers.
6. Keep all application processes stateless and all private data services off the public network.
7. Use direct-to-R2 uploads and asynchronous media processing.
8. Enforce tenant isolation and object-level authorization in backend services and SQL.
9. Make AI optional, budgeted, source-grounded, and permission-aware.
10. Validate each phase with real users and measurable exit criteria.
11. Scale vertically, then add replicas, then optimize/partition data, then extract services only when evidence supports it.
12. Treat backups, restore drills, observability, security, documentation, and support as part of feature completion.
13. Do not add school, hospital, live streaming, or other high-risk/later modules to the core launch without a separate approved plan.
14. Keep this plan, ADRs, and `docs/STATUS.md` aligned with the running code.

---

## Appendix A — Feature Inventory from the Production Blueprint

### Reported as already built — must be independently verified

- Signup, login, logout, secure cookies and CSRF.
- Google sign-in, Turnstile, breached-password check.
- Photo/video upload via presigned URL, AVIF/WebP, HLS video, text overlay.
- Feed with fan-out on write, celebrity merge on read, buffered counters, For You tab.
- Likes and notifications via event dispatcher.
- Hybrid keyword + vector search with RRF and SQL visibility filtering.
- RAG assistant with tenant filter.
- Image moderation (requires configured provider key).
- Basic MCP server with draft-only writes.
- Public business page.
- Admin panel, roles, test data batches, demo data.

**Verification rule:** Do not mark these as complete until a working test, staging demonstration, and code inspection support the claim.

### Planned feature inventory

| Feature group | Scope | Phase |
|---|---|---|
| Production base | Outbox, permissions, audit, rate limits, backups/restore, monitoring, staging, CI/CD | 1 |
| Business daily tool | Services, slots, bookings, calendar, reminders, reviews/replies, quotation, local search, inbox | 2 |
| Viral growth | Card templates, festival frames, albums, slideshows, referrals, QR, OG share cards | 3 |
| Social complete | Threaded comments, follow requests, block/mute/restrict, saves, mentions, hashtags, stories/highlights, DMs, groups, voice notes, reels | 4 |
| Events and shop | Organizer, packages, vendors, availability, products, orders, order status, bulk order | 5 |
| Money | Razorpay, UPI/cards, advance deposits, plans, verification, boosts, local promotion, tips, payouts, GST invoice | 6 |
| Calls and AI plus | LiveKit, captions, hashtags, alt text, subtitles, translation, toxic-comment warning, spam detection, business assistant | 7 |
| Scale | Replicas, partitions, orchestration, selective service extraction | 8, metrics-triggered |

---

## Appendix B — Core Engineering Decisions to Preserve

- Keep the `emit()` call interface if practical, but change its implementation to transactional outbox insertion.
- Use one permission map and object-level checks in services.
- Use cursor pagination for large collections.
- Use integer paise for all money.
- Use UTC timestamps and display in user timezone.
- Use unique idempotency keys for booking/order/payment operations.
- Use database constraints for booking overlap and inventory integrity.
- Use R2 object keys in the database, not public URLs as the source of truth.
- Use signed URLs for private media.
- Use a model/version field for every embedding.
- Filter RAG retrieval by owner/tenant and visibility in SQL.
- Never index DMs.
- Treat user-generated and retrieved text as untrusted.
- Keep MCP tools on the same service and permission layer as the API.
- Keep Celery beat to one active scheduler.
- Use expand-and-contract database migrations.
- Add read replicas, partitions, Kafka, Kubernetes, or microservices only after a measured need and an ADR.

---

## Appendix C — Glossary

| Term | Meaning |
|---|---|
| Modular monolith | One deployable application organized into independent domain modules |
| Outbox | Database table storing events in the same transaction as business data |
| Idempotency | Repeating the same request/event does not repeat its side effect |
| Tenant isolation | One business/user cannot read or change another tenant's data |
| R2 | Cloudflare object storage used for media files |
| HLS | HTTP Live Streaming video format |
| pgvector | PostgreSQL extension for vector similarity search |
| RRF | Reciprocal Rank Fusion; combines ranked search result lists |
| RAG | Retrieval-Augmented Generation; AI answers using permission-filtered source material |
| MCP | Model Context Protocol; standard interface for AI tools |
| SLO | Service Level Objective; measurable reliability/performance target |
| RPO | Maximum acceptable data-loss window |
| RTO | Target time to restore service |
| ADR | Architecture Decision Record |
| PWA | Progressive Web App |
| BOLA/IDOR | Broken Object Level Authorization / Insecure Direct Object Reference |
| Expand-contract migration | Safe schema evolution across multiple application releases |
