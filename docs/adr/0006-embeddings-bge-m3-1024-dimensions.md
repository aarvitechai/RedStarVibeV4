# ADR 0006: Embeddings: bge-m3, 1024 dimensions

- Status: Accepted
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
Older docs mentioned 512 and 1536 dimensions.

## Decision
Use bge-m3 (1024 dims, multilingual incl. Hindi) via Workers AI. Every vector row stores model and version; only vectors of one model are compared. A separate `hash-v1` fallback exists for AI_PROVIDER=none.

## Consequences
A model change means a background re-embed backfill.
