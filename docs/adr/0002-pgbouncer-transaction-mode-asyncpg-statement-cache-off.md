# ADR 0002: PgBouncer transaction mode; asyncpg statement cache off

- Status: Accepted
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
Many app copies need few DB connections. Transaction pooling breaks prepared-statement caching and session state.

## Decision
Use PgBouncer in transaction mode in deployed environments. `RSV_DB_PGBOUNCER=true` disables asyncpg statement caches. No session-level state (SET, session advisory locks, temp tables).

## Consequences
Restart PgBouncer after column type changes.
