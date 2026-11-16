# ADR 0012: Schema per module

- Status: Accepted
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
Docs disagreed: one schema per module vs a flat public schema.

## Decision
Each module owns its own PostgreSQL schema. No cross-schema foreign keys; keep the id and ask the owning service.

## Consequences
This repository is new, so there are no legacy `public` tables to keep.
