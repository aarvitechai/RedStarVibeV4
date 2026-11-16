# RedStarVibe Project Status

Updated: 2026-11-16
Current phase: Phase 2 — business daily tool (code complete locally; pilot validation not started)
Release: none deployed. Local stack verified at http://localhost:8090 (see `docs/setup.md`).

## Phase status
- [x] Phase 0 — Repository audit and engineering setup (`docs/audit/phase-0-audit.md`)
- [ ] Phase 1 — Production base (+ accounts/auth, ADR 0017) — code done; hosting items open (checklist below)
- [ ] Phase 2 — Business daily tool — code done; exit criterion (20 real businesses, 2 weeks) not started
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

## Phase 2 checklist
| Item | Status | Evidence |
|---|---|---|
| Business page: create, edit, reserved/unique slug, encrypted phone, role promotion | done | `tests/test_business_booking.py` |
| Public SSR page `/business/[slug]` with OG tags | done | `infra/scripts/smoke_e2e.sh` step 9 |
| Services (paise prices, duration, buffer), hours, bookable resources | done | tests |
| Owner-only management (404 for non-owners), permission checks | done | `test_other_users_cannot_manage_a_business` |
| Slots API (hours, duration, buffer, lead time, per-resource availability) | done | slot unit test + API test |
| Booking create with required Idempotency-Key; replay returns same booking | done | `test_idempotency_key_replay_returns_same_booking` |
| No double booking: DB exclusion constraint + concurrent race test | done | `test_two_customers_race_for_one_slot_exactly_one_wins`, direct-insert test |
| Status machine (confirm, complete, cancel, expire) with history | done | `test_status_machine_and_permissions` |
| Reminders (beat, every minute, once only) and expiry (every 5 min) | done | `test_reminders_and_expiry_jobs` |
| Reviews only after completed bookings; owner replies | done | `test_review_only_after_completion_and_owner_reply` |
| In-app notifications from booking events, idempotent | done | test + smoke step 8 (real worker) |
| Nearby search (PostGIS, radius, category) | done | `test_nearby_search` |
| Web: dashboard, booking widget, my bookings + review, notifications, near-me | done | build passes; manual check pending |
| Web push, email, SMS/WhatsApp channels | **open** | needs providers (Blueprint 25) |
| Holidays / closures, quotation requests, business inbox, analytics | **open** | Phase 2 backlog |
| Pilot: 20 real businesses taking bookings for 2 weeks | **not started** | needs hosting + onboarding |

## Verified features
| Feature | Status | Evidence / test | Owner |
|---|---|---|---|
| Authentication | working (local) | 33 backend tests; gateway smoke test | — |
| Admin: audit log, role changes | working (API only) | tests | — |
| Posts/media | not implemented | | |
| Feed | not implemented | | |
| Notifications (in-app) | working (local) | tests + smoke | — |
| Search | not implemented | | |
| RAG assistant | not implemented | | |
| Image moderation | not implemented | | |
| MCP | not implemented | | |
| Business page + booking | working (local) | 50 backend tests; `infra/scripts/smoke_e2e.sh` | — |
| Admin panel UI | not implemented | | |

## Current blockers
- No hosting accounts (VM, Cloudflare, R2, domain DNS), so there is no staging or public URL.
- An earlier RedStarVibe codebase exists at `../../RedStarVibe` (its Docker stack auto-starts and uses port 8080). Decide whether V4 replaces it or should reuse parts of it (see ADR 0017 note).
- ADR 0016 (branch flow) awaits product-owner confirmation.

## Production metrics
- API p95: n/a · Error rate: n/a · Queue oldest-job age: n/a · DB connection utilization: n/a
- Backup last success: n/a · Restore last tested: 2026-11-16 (local only) · AI cost / active user: n/a
