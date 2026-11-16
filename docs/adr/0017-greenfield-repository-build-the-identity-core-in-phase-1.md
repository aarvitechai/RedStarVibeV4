# ADR 0017: Greenfield repository: build the identity core in Phase 1

- Status: Accepted
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
Blueprint v4 assumes a running codebase where auth, posts, feed, search, RAG, MCP, business page and admin already exist. The Phase 0 audit found that this repository contains no application code.

## Decision
Every feature listed as already built is marked `not implemented` in docs/STATUS.md. Accounts and auth (signup, login, sessions, CSRF, roles) are built in Phase 1 with the production base, because the permission map, audit log and every later phase depend on them. Posts, feed, search, RAG and MCP move into Phase 4 and Phase 7 scope.

## Consequences
Phase 1 grows, so the Blueprint timeline must be re-estimated.

## Note (2026-11-16, Phase 1)
During Phase 1, Docker Desktop auto-started a separate, older `redstarvibe` Compose project located at
`E:\Practice\RealAIProject\RedStarVibeProject\RedStarVibe` (services: gateway, web, api, ws, mcp, worker, beat,
pgbouncer, objectstore, livekit, db). This is very likely the codebase the Blueprint describes as "already built".
It was not inspected or modified. The product owner should decide whether V4 is a clean rebuild (this ADR stands)
or should port verified parts of that codebase (supersede this ADR).
