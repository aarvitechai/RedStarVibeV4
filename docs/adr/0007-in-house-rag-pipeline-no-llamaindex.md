# ADR 0007: In-house RAG pipeline, no LlamaIndex

- Status: Accepted
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
Older docs used LlamaIndex.

## Decision
Keep retrieval in `app/ai/rag` with plain SQL so the tenant and visibility filter is applied in SQL and fully under our control.

## Consequences
Fewer dependencies; we own chunking, retrieval and reranking code.
