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
