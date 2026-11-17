# Runbook: measure, then scale (Phase 8)

Rule: find the dominant bottleneck with evidence, change one thing, re-measure, keep it only if it helps (ADR 0020).

## 1. Watch
- Monitoring stack: `docker compose --profile monitoring up -d` → Grafana http://localhost:3001 ("RedStarVibe SLOs"),
  Prometheus http://localhost:9090 (alerts tab). Set `RSV_GRAFANA_PASSWORD` outside local.
- Panels: p95/p99, slowest routes, 5xx rate, booking-create p95, outbox lag, queue depth, dead letters, DB connections, WebSockets.

## 2. Load test (staging, before each phase exit and release)
```
docker run --rm -i --network <project>_public -e BASE=http://gateway:8080 -e DURATION=5m grafana/k6:1.3.0 run - < infra/scripts/load/baseline.js
```
Knobs: `RATE` (multiplier, default 1 ≈ 57 req/s mix), `CUSTOMERS`, `DURATION`. The setup step creates its own data and
needs a high `RSV_RATE_LIMIT_SIGNUP_PER_HOUR` on the target (staging only). Pass bar: reads p95 < 200 ms,
booking create p95 < 300 ms, no 5xx.

## 3. Find the bottleneck (in this order)
1. CPU per process: `docker stats`. API near `workers × 100%` → CPU bound; profile:
   `python -m scripts.profile_hot_paths 100` (test DB) for per-path wall/CPU time, SQL count and top functions.
2. Postgres: `select wait_event_type, wait_event, state, count(*) from pg_stat_activity group by 1,2,3` during load.
   `IO:WALSync` on COMMIT → disk fsync (`pg_test_fsync`); `Lock:*` → contention; many `idle in transaction` → the app is slow.
3. Queues and outbox: Grafana panels; worker CPU.

## 4. Levers (cheapest first)
| Level | Lever | How |
|---|---|---|
| 1 | Query count / N+1 / indexes | profiler SQL count, `EXPLAIN ANALYZE` |
| 1 | Middleware/framework overhead | pure ASGI middleware (done) |
| 1 | Worker count | `RSV_API_WORKERS` (measure; more is not always better) |
| 1 | Caches (Blueprint 13.2) | business page 60 s, slots 30 s (purge on booking), anonymous search 60 s |
| 2 | PgBouncer | `--profile scale`; `RSV_DATABASE_URL=...@pgbouncer:6432/...`, `RSV_DB_PGBOUNCER=true` |
| 2 | Separate media/AI workers | `--profile scale` + `RSV_WORKER_QUEUES=default` on the main worker |
| 2 | API / ws replicas | `docker compose up -d --scale api=2 --scale ws=2` (stateless; ws fan-out via Redis pub/sub) |
| 3+ | Replicas, partitions, extraction | capacity report + ADR first |

## 5. Record
Write `docs/capacity/YYYY-MM-DD-<topic>.md`: observed metric, window, root cause, options, cost, expected gain, rollback, owner.
