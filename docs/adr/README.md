# Architecture Decision Records

One file per decision: `NNNN-short-title.md` with Status (Proposed, Accepted or Superseded), Context, Decision and Consequences. Copy `template.md` for a new ADR. Never rewrite an accepted decision; supersede it with a new ADR.

| ADR | Title | Status |
|---|---|---|
| 0001 | Modular monolith with separate process types | Accepted |
| 0002 | PgBouncer transaction mode; asyncpg statement cache off | Accepted |
| 0003 | Next.js server container behind nginx, not Cloudflare Pages | Accepted |
| 0004 | Hand-written UI primitives; picture element instead of next/image | Accepted |
| 0005 | SeaweedFS emulates R2 locally | Accepted |
| 0006 | Embeddings: bge-m3, 1024 dimensions | Accepted |
| 0007 | In-house RAG pipeline, no LlamaIndex | Accepted |
| 0008 | pgvector until about 10M vectors or search p95 over 150 ms | Accepted |
| 0009 | Cloudflare Workers AI by default; no self-hosted GPU | Accepted |
| 0010 | One error response shape | Accepted |
| 0011 | Transactional outbox for events | Accepted |
| 0012 | Schema per module | Accepted |
| 0013 | Roles plus a central permission map | Accepted |
| 0014 | MCP served at /mcp behind the gateway | Accepted |
| 0015 | Minimum age 18+ | Accepted |
| 0016 | Branch and environment flow | Proposed |
| 0017 | Greenfield repository: build the identity core in Phase 1 | Accepted |
| 0018 | Booking model and module dependencies | Accepted |
