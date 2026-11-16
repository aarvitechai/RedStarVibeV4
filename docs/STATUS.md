# RedStarVibe Project Status

Updated: 2026-11-16
Current phase: Phase 1 — production base (code complete locally; hosting-dependent items open)
Release: none deployed. Local stack verified at http://localhost:8090 (see `docs/setup.md`).

## Phase status
- [x] Phase 0 — Repository audit and engineering setup (`docs/audit/phase-0-audit.md`)
- [ ] Phase 1 — Production base (+ accounts/auth, ADR 0017) — see checklist below
- [ ] Phase 2 — Business daily tool
- [ ] Phase 3 — Viral growth
- [ ] Phase 4 — Social complete
- [ ] Phase 5 — Events and shop
- [ ] Phase 6 — Money
- [ ] Phase 7 — Calls and AI plus
- [ ] Phase 8 — Scale (metrics-triggered)

## Phase 1 checklist
| Item | Status | Evidence |
|---|---|---|
| Accounts: signup (18+, reserved usernames, password rules), login, logout | done | `tests/test_accounts.py`; e2e smoke through gateway |
| Argon2id hashing, rehash on login | done | `test_password_is_hashed_with_argon2id` |
| 15-min access JWT + 30-day rotating refresh, reuse revokes the family | done | `test_refresh_rotates_and_reuse_revokes_family` |
| HttpOnly/Secure/SameSite cookies, `__Host-` prefix when deployed | done | `app/core/cookies.py` |
| CSRF double-submit on every mutating `/api/` call | done | `test_mutation_without_csrf_is_rejected` |
| Login activity, session list, log out other devices | done | `test_logout_other_devices` |
| Rate limits: login (5/min/account, 20/min/IP), signup (10/h/IP) | done | `test_login_wrong_password_then_rate_limited` |
| Central permission map + `require_permission()`; role read from DB | done | `test_permissions_audit_outbox.py` |
| Append-only audit log (DB trigger) | done | `test_audit_log_is_append_only` |
| Superadmin only via `scripts/make_superadmin.py` | done | `test_role_change_by_superadmin_is_audited` |
| Transactional outbox, relay (beat 2 s), idempotent dispatcher, dead letter | done | outbox tests; e2e: signup event relayed and consumed in Docker |
| Health/readiness endpoints | done | Phase 0 |
| Restore drill script | done (local) | drill PASSED 16 s — `docs/runbooks/backup-restore.md` |
| Nightly encrypted backup script | written, not scheduled | needs backup bucket + age key |
| CI: lint, types, unit + integration tests, contract check, audits, image scan | written | first GitHub run pending |
| Deploy workflow (staging auto, production approval) | written | needs VM + GitHub Environments secrets |
| Staging environment, Cloudflare Tunnel/Access | **open** | needs hosting accounts |
| Sentry, Prometheus/Grafana, alerts | **open** | needs hosting |
| MFA (TOTP/passkeys) for staff/admin | **open** | backlog |
| Breached-password check (HIBP), Turnstile on signup | **open** | needs provider keys |
| Email verification | **open** | needs email provider |

## Verified features
| Feature | Status | Evidence / test | Owner |
|---|---|---|---|
| Authentication | working (local) | 33 backend tests; gateway smoke test | — |
| Admin: audit log, role changes | working (API only) | tests | — |
| Posts/media | not implemented | | |
| Feed | not implemented | | |
| Likes/notifications | not implemented (event plumbing only) | | |
| Search | not implemented | | |
| RAG assistant | not implemented | | |
| Image moderation | not implemented | | |
| MCP | not implemented | | |
| Business page | not implemented | | |
| Admin panel UI | not implemented | | |

## Current blockers
- No hosting accounts (VM, Cloudflare, R2, domain DNS), so there is no staging or public URL.
- An earlier RedStarVibe codebase exists at `../../RedStarVibe` (its Docker stack auto-starts and uses port 8080). Decide whether V4 replaces it or should reuse parts of it (see ADR 0017 note).
- ADR 0016 (branch flow) awaits product-owner confirmation.

## Production metrics
- API p95: n/a · Error rate: n/a · Queue oldest-job age: n/a · DB connection utilization: n/a
- Backup last success: n/a · Restore last tested: 2026-11-16 (local only) · AI cost / active user: n/a
