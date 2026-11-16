# ADR 0001: Modular monolith with separate process types

- Status: Accepted
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
Source documents considered microservices and Kubernetes from early phases.

## Decision
One backend codebase and image, organised as domain modules, run as separate processes (api, ws, mcp, worker, beat, migrate). A module is extracted only when metrics prove the need (chat, feed, media first).

## Consequences
Simple to run on one VM; boundaries (router > service > repository, no cross-module table access) keep extraction a move, not a rewrite.
