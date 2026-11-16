# ADR 0014: MCP served at /mcp behind the gateway

- Status: Accepted
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
Older docs used mcp.redstarvibe.com.

## Decision
Serve MCP at `/mcp` through nginx. A subdomain can be added later if needed.

## Consequences
One TLS entry and one WAF policy.
