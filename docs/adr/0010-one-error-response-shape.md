# ADR 0010: One error response shape

- Status: Accepted
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
Source docs had two error shapes.

## Decision
Every endpoint returns `{"error": {"code", "message", "details", "request_id"}}`, implemented in `app/core/errors.py`. No stack traces or provider internals reach clients.

## Consequences
Clients handle one shape; `request_id` links user reports to logs.
