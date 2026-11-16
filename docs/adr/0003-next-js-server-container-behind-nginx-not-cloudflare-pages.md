# ADR 0003: Next.js server container behind nginx, not Cloudflare Pages

- Status: Accepted
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
Older docs proposed static hosting on Cloudflare Pages.

## Decision
Run Next.js as a server container behind the nginx gateway; Cloudflare CDN caches static assets. A strict per-request CSP nonce is set in `apps/web/src/proxy.ts`; the root layout reads request headers so every page renders per request and receives the nonce.

## Consequences
Pages are server-rendered (no static prerender). Public pages are cached at the CDN/Redis layer with short TTLs instead.
