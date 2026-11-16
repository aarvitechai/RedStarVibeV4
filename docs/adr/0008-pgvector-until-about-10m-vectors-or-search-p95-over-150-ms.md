# ADR 0008: pgvector until about 10M vectors or search p95 over 150 ms

- Status: Accepted
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
Older docs moved to Qdrant from Phase 3.

## Decision
Stay on pgvector (HNSW) inside PostgreSQL. Revisit only when a trigger is met.

## Consequences
One database to run and back up.
