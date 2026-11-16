# ADR 0019: AI layer, MCP authentication and calls

- Status: Accepted (MCP auth: interim)
- Date: 2026-11-16
- Source: Phase 7 implementation

## Context
Phase 7 adds AI helpers, hybrid search, the RAG assistant, the MCP server and LiveKit calls. Provider accounts
(Cloudflare Workers AI, Anthropic, LiveKit Cloud) do not exist yet, and the platform must work fully without them.

## Decision
- **AI providers** sit behind `app/ai/providers.py`. `AI_PROVIDER=none` is a real mode: hash-v1 embeddings (separate
  model name, never compared with bge-m3), rule-based hashtags and toxicity, extractive assistant answers. Every
  AI call goes through `app/ai/gateway.py`, which provides per-plan daily quotas, a global budget switch, a
  circuit breaker and an `ai.ai_calls` log row. Prompts are versioned files in `app/ai/prompts/`.
- **Search**: one `search.documents` table for posts, businesses and help articles. Keyword search uses tsvector + GIN
  and meaning uses pgvector HNSW, merged with RRF (k = 60). Visibility, owner and block filters are applied in SQL.
  Chat is never indexed. The assistant uses OR keyword matching, a score threshold that leads to "I don't know",
  sources wrapped as untrusted data, and citations.
- **MCP** is served at `/mcp` as JSON-RPC 2.0 (initialize, tools/list, tools/call). It is authenticated with
  **personal access tokens** (scopes `read` and `write:drafts`, 30 days, stored hashed, audited, 60 calls/min).
  Writes create drafts only. OAuth 2.1 + PKCE (Blueprint 11.4) replaces manual tokens before public launch.
- **Calls**: the API issues 5-minute LiveKit JWTs only after membership and block checks, and rings over the
  WebSocket hub. Locally a `livekit-server --dev` container runs; ports are configurable because ICE
  advertises them.

## Consequences
- Every AI feature has a non-AI path; a provider outage never takes a feature down.
- Switching to Workers AI changes the embedding model, so run `search.reembed_stale` as a backfill.
- MCP OAuth, Whisper subtitles and translation need provider keys; they are ready in code but untested against
  real providers.
