# ADR 0011: Transactional outbox for events

- Status: Accepted
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
Commit-then-emit loses events if the process dies between the two.

## Decision
`emit()` writes to `notify.outbox` in the same transaction as the business row. A beat-driven relay publishes to Celery; consumers are idempotent (processed event_id table); failures go to a dead-letter table.

## Consequences
First task of Phase 1.
