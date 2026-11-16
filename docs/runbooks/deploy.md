# Runbook: deploy and rollback

Flow (ADR 0016, proposed): feature → `dev` → `staging` (auto-deploys stage.redstarvibe.com) → `production` (required reviewer).

## What the deploy workflow does (`.github/workflows/deploy.yml`)
1. Build backend and web images, tag with the git SHA, push to GHCR.
2. SSH to the target VM (via Cloudflare Tunnel / Access), write `RSV_IMAGE_TAG=<sha>`.
3. `docker compose pull` → `docker compose run --rm migrate` (expand-only migrations) → `docker compose up -d`.
4. Wait for `/health/ready` (max 120 s); fail the job otherwise.
5. Smoke test: `GET /`, `GET /api/v1/meta`.

## One-time setup (not done yet — needs accounts)
- VM with Docker, the repo checked out at `/opt/redstarvibe`, `.env` from the secret manager.
- Cloudflare Tunnel to `gateway:8080`; Cloudflare Access in front of staging.
- GitHub Environments `staging` and `production` with secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`; production has Required reviewers.

## Rollback
- App: re-run the workflow for the previous commit (or on the VM: `RSV_IMAGE_TAG=<previous-sha> docker compose up -d`).
- Data: migrations are expand-then-contract, so the previous image works with the new schema. Irreversible data changes are forward-fixed.
- Auto rollback trigger: 5xx rate > 2 % in the first 10 minutes (alert → on-call rolls back).
