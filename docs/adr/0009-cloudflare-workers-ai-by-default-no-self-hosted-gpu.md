# ADR 0009: Cloudflare Workers AI by default; no self-hosted GPU

- Status: Accepted
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
Older docs self-hosted BGE, Whisper and CLIP on GPU workers.

## Decision
`AI_PROVIDER=none|cloudflare|anthropic`. Default cloudflare (embeddings, vision, Whisper, small LLM); Claude optional for harder reasoning. Providers sit behind an adapter with timeouts, a circuit breaker and a non-AI fallback.

## Consequences
No GPU cost at launch; self-host only when the bill says so.
