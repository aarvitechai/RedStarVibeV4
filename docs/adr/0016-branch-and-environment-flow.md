# ADR 0016: Branch and environment flow

- Status: Proposed
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
The Blueprint describes trunk-based development where merging to main deploys staging. The repository has dev, staging, production and main branches.

## Decision
Feature branches open PRs into `dev` (integration; CI on every PR). A PR from `dev` into `staging` deploys stage.redstarvibe.com. A PR from `staging` into `production` deploys production after a required reviewer approves (GitHub Environment). `main` is fast-forwarded to `production` after each release and stays the default branch. Hotfixes branch from `production` and are merged back into staging and dev.

## Consequences
Needs product-owner confirmation before deploy workflows are wired (Phase 1, week 3).
