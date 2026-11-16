# ADR 0005: SeaweedFS emulates R2 locally

- Status: Accepted
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
Older docs used MinIO for local S3.

## Decision
Use SeaweedFS (S3 API) locally and Cloudflare R2 in staging and production, through one S3 client. Added to docker-compose together with the media module.

## Consequences
Same S3 code path everywhere.
