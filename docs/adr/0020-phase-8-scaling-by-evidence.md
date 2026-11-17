# ADR 0020: Phase 8 — scale by evidence; what is done now and what waits for triggers

- Status: Accepted
- Date: 2026-11-17
- Source: Execution Plan §14 Phase 8, §18.3; Blueprint 13, 19.3, 27.6; capacity report 2026-11-17

## Context
Phase 8 is triggered by production metrics. There is no production traffic yet. The plan forbids adding
infrastructure (replicas, partitions, Kafka, Kubernetes, microservices) without a measured need, and requires one
scaling change at a time.

## Decision
Done now (measurement and Level 1, plus Level 2 *readiness* switched off by default):
- Prometheus metrics in the app (RED per route template, outbox lag, dead letters, queue depth, DB pool,
  WebSockets), Prometheus with the Blueprint 18.1 alert rules, a provisioned Grafana SLO dashboard
  (`docker compose --profile monitoring`).
- k6 baseline (`infra/scripts/load/baseline.js`) and an in-process profiler (`scripts/profile_hot_paths.py`).
- Level 1 fixes found by measurement: pure ASGI middleware instead of BaseHTTPMiddleware (reads p95 1.86 s -> 195 ms
  at the same load), no duplicate gunicorn access log, no duplicate lookups when creating bookings.
- Level 2 pieces behind `--profile scale`: PgBouncer (transaction mode, ADR 0002) and a separate media/AI worker
  pool. `RSV_API_WORKERS` sets the gunicorn worker count (default 2; 4 showed no gain locally).

Deferred until a trigger in Execution Plan §18.3 persists through representative peaks:
| Change | Trigger |
|---|---|
| Second app VM / API replicas | API p95 over SLO after Level 1 work, or CPU above 70% for a week |
| Managed Postgres + PITR + read replica | DB over 20 GB, restore over 1 h, or primary read contention |
| Separate media worker (profile `scale`) | media queue above 500 for 30 min daily |
| Redis caches for business page / slots / anonymous search (Blueprint 13.2) | those routes in the slowest p95 panel at peak |
| Message/notification/analytics partitioning | table size or query plans show the need |
| Kafka, Kubernetes, service extraction | only Level 5 evidence; each needs its own ADR |

## Consequences
- The write path's local p95 is bound by the developer machine's disk fsync (5.4 ms/op on Docker Desktop). A
  diagnostic run with asynchronous commit met all targets. Production keeps `synchronous_commit = on`
  (RPO), so staging on real SSD storage must re-run the baseline before launch.
- Every scaling step produces a capacity report: metric, window, cause, options, cost, expected gain, rollback, owner.
