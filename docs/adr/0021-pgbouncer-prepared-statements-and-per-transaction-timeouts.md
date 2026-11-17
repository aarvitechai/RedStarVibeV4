# ADR 0021: PgBouncer keeps prepared statements; timeouts are set per transaction

- Status: Accepted (amends ADR 0002)
- Date: 2026-11-17
- Source: Phase 8 Level 2 verification, `docs/capacity/2026-11-17-baseline.md`

## Context
ADR 0002 chose PgBouncer in transaction mode with the asyncpg statement cache off. Phase 8 ran the app through
PgBouncer for the first time and found:
1. **It did not work at all.** The app sends `statement_timeout` and `idle_in_transaction_session_timeout` as
   connection startup parameters. PgBouncer refuses them (`unsupported startup parameter`), so every connection
   failed and `/health/ready` reported the database as down.
2. **With the statement cache off, every request took ~11 ms longer** (business page 28 ms vs 16.6 ms direct,
   one request at a time), and under the k6 baseline the app pool ran out: p95 30 s, 11.5% of requests failed.
   PgBouncer reported 26 ms per query.
3. PgBouncer 1.21+ supports protocol-level prepared statements in transaction mode (`max_prepared_statements`).
   We pin 1.24.1. With it on and the cache kept, the per-request cost fell to ~1.8 ms and errors went to 0.
4. The worker built its own engine without any statement timeout.

## Decision
- Behind PgBouncer (`RSV_DB_PGBOUNCER=true`) only `timezone` is sent at connect time. Both timeouts are applied
  to every transaction with `set_config(..., is_local => true)`, which ends with the transaction and so cannot
  leak to the next PgBouncer client. Direct connections keep startup parameters (no extra statement).
- PgBouncer runs with `MAX_PREPARED_STATEMENTS=500`, and the asyncpg statement caches stay **on**
  (`RSV_DB_PGBOUNCER_PREPARED_STATEMENTS=true`, default). Set it to false only for PgBouncer older than 1.21.
- The API, ws, MCP and worker processes all build their engine with `app.core.database.build_engine`.
- ADR 0002's rule "no session-level state (SET, session advisory locks, temp tables)" still applies.

## Consequences
- PgBouncer is usable (smoke test 26/26, 0 errors under load) but stays **off** by default. With one API copy
  locally it still added latency (p95 ~3 s against ~0.15 s direct) through the extra network hop, while the
  database used 33 of 100 connections. Switch it on when DB connections pass 70% of `max_connections` or a
  second app VM is added, and re-measure on staging first.
- Tests: `tests/test_worker_runtime.py` covers the per-transaction timeouts, that nothing leaks after the
  transaction, and the worker's timeouts.
