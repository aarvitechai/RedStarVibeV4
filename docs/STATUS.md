# RedStarVibe Project Status

Updated: 2026-11-16
Current phase: Phases 0–7 code complete locally; pilot validation and hosting not started
Release: none deployed. Full local stack verified end to end at http://localhost:8090 (`infra/scripts/smoke_e2e.sh`, 26 steps).

## Phase status
- [x] Phase 0 — Repository audit and engineering setup (`docs/audit/phase-0-audit.md`)
- [ ] Phase 1 — Production base (+ accounts/auth, ADR 0017) — code done; hosting items open (checklist below)
- [ ] Phase 2 — Business daily tool — code done; exit criterion (20 real businesses, 2 weeks) not started
- [ ] Phase 3 — Viral growth — code done; exit criterion (10% of actives share weekly) needs real users
- [ ] Phase 4 — Social complete — code done; exit criterion (Day-7 retention improving) needs real users
- [ ] Phase 5 — Events and shop — code done; exit criterion (5 event companies + 10 shops live) needs pilot
- [ ] Phase 6 — Money — code done with sandbox; real Razorpay needs keys + webhook URL; exit needs first real paid plan
- [ ] Phase 7 — Calls and AI plus — code done with `AI_PROVIDER=none` + local LiveKit; real providers need keys; exit needs real AI cost data
- [ ] Phase 8 — Scale (metrics-triggered) — tooling + Level 1 fixes done (ADR 0020, `docs/capacity/2026-11-17-baseline.md`); further steps wait for production triggers

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
| CI: lint, types, unit + integration tests, contract check, audits, image scan, Playwright e2e on the full stack | done | GitHub Actions green on `dev` |
| Deploy workflow (staging auto, production approval) | written | needs VM + GitHub Environments secrets |
| Staging environment, Cloudflare Tunnel/Access | **open** | needs hosting accounts |
| Sentry, Prometheus/Grafana, alerts | **open** | needs hosting |
| MFA: TOTP two-factor login, mandatory for staff/admin/superadmin (403 until enabled), replay-safe codes | done | `tests/test_mfa.py`, `e2e/tests/two-factor.spec.ts` (passkeys still open) |
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
| Web: dashboard, booking widget, my bookings + review, notifications, near-me | done | Playwright journeys at 360/768/1280 |
| Web push, email, SMS/WhatsApp channels | **open** | needs providers (Blueprint 25) |
| Holidays / closures, quotation requests, business inbox, analytics | **open** | Phase 2 backlog |
| Pilot: 20 real businesses taking bookings for 2 weeks | **not started** | needs hosting + onboarding |

## Phase 3 checklist
| Item | Status | Evidence |
|---|---|---|
| Media: presigned direct upload (10 min), magic-byte validation, EXIF/GPS strip, WebP+AVIF 320/640/1080, raw deleted | done | `tests/test_phase3_growth.py`; smoke steps 11–12 |
| Video/voice processing (H.264 MP4 + poster, AAC) with duration limits | done (code) | exercised in Phase 4 |
| SeaweedFS locally (ADR 0005), R2-ready storage adapter | done | smoke |
| Card templates as data (9 incl. Hindi), idempotent render by input hash, watermark, licensed Noto fonts | done | tests + smoke step 13 |
| Public card page `/c/[id]` with OG image; share counter | done | smoke |
| 1200×630 business share image, `og:image` on business pages | done | test + smoke step 14 |
| QR codes for own pages only (business, invite) | done | `test_share_image_and_qr` |
| Referral codes/links, attribution on signup, qualify on first booking, append-only points ledger, no double award, self-referral blocked | done | referral tests |
| Albums: flipbook share page, private albums, owner-only photos, slideshow MP4 (FFmpeg, on request) | done | tests + smoke step 15 |
| Licensed music for slideshows, festival story frames, A/B test of share flow | **open** | needs licensed assets |
| Points 7-day pending period, device/IP fraud limits, leaderboard | **open** | backlog (Blueprint 26.4) |

## Phase 4 checklist
| Item | Status | Evidence |
|---|---|---|
| Profiles, private accounts, follow requests (approve/decline), user search | done | `tests/test_phase4_social.py` |
| Block (both directions, removes follows, hides profile/posts/comments/search/DM) and mute | done | `test_block_hides_everything_both_ways` |
| Posts with photos/videos, visibility, hashtags + hashtag pages, mentions, likes (idempotent), threaded comments, saves | done | `test_post_with_photo_like_comment_save` |
| Feed: fan-out on write to Redis (800 cap, 7 d TTL), celebrity merge on read, DB fallback, read-time re-check of follows/blocks | done | feed tests + smoke step 16 |
| Stories (24 h), viewers list (author only), highlights | done | `test_stories_tray_views_and_expiry` |
| DMs + groups: persisted first, gap-free per-conversation seq under concurrency, client-id dedupe, after_seq catch-up, unread/read receipts, typing, owner controls | done | chat tests |
| WebSocket `ws` process: cookie auth, Origin check, 25 s heartbeat, Redis pub/sub across replicas, clean task shutdown | done | smoke step 17 (real socket) |
| Voice notes (audio upload → AAC) and reels (single video, reels feed) | done | code + media pipeline; UI wired |
| Reports + staff moderation queue; removal applied by owning module via event; audited | done | `test_report_and_moderator_removal` |
| Like/view counters buffered in Redis (flush every 5 s) | **open** | direct atomic UPDATE today (fine at launch scale) |
| Messages monthly partitioning, web push for offline users, HLS for reels | **open** | needs scale / VAPID keys |
| Close friends, restrict, story frames | **open** | backlog |

## Phase 5 checklist
| Item | Status | Evidence |
|---|---|---|
| Products with stock, SKU, photos; owner sees exact stock, public sees availability | done | `tests/test_phase5_events_shop.py` |
| Orders: atomic conditional stock decrement (8 concurrent buyers, stock 3 -> exactly 3), Idempotency-Key, encrypted delivery address, bulk order with date, note | done | `test_concurrent_orders_never_oversell`, idempotency test |
| Order status flow (placed→confirmed→ready/shipped→delivered), customer cancel before confirm, cancel restores stock, history | done | status tests |
| Packages (silver/gold/platinum/custom) with items and vendors; vendor must have accepted the invite | done | `test_package_requires_accepted_vendor` |
| Vendor network: invite, accept/decline | done | tests |
| Unified calendar: one hold per organizer + vendor, EXCLUDE constraint blocks a vendor across organizers; vendor sees only own holds | done | `test_gold_package_blocks_all_vendors_across_organizers` |
| Unpaid holds expire after 48 h (beat); cancellation releases holds; advance payment locks the date (Phase 6) | done | `test_event_booking_rules_idempotency_and_release` |
| Web: shop + order management and packages/vendors/event bookings in dashboard; cart + package booking on public page; My orders | done | build passes |
| Returns/delivery policy pages, vendor disputes process, shipping integration | **open** | operational policy needed |

## Phase 6 checklist
| Item | Status | Evidence |
|---|---|---|
| Payment intents: amount computed server-side (client cannot send one), Idempotency-Key, reuse of open intent, ownership | done | `tests/test_phase6_payments.py` |
| Razorpay adapter (orders, payments lookup, refunds, HMAC webhook verify, bounded retries, 5 s timeout); sandbox provider locally, refused in staging/prod | done | code; sandbox exercised by tests |
| Only verified webhooks mark paid; unique provider event id (duplicates ignored); amount mismatch never marks paid; payload redacted | done | webhook tests |
| Reconciliation job every 15 min recovers lost webhooks | done | `test_reconciliation_recovers_a_lost_webhook` |
| Append-only ledger (charge, platform fee 2% orders / 5% events, refunds), payout summary per business | done | ledger + payout tests |
| Refunds (full/partial) by business owner or admin, audited | done | `test_refund_by_owner_only` |
| Event advance (20%) locks the date (hold no longer expires) | done | `test_advance_payment_locks_event_date` |
| Plans as data (Free/Premium/Creator/Business) + subscriptions + entitlements (AI quota source) | done | `test_subscription_sets_entitlements` |
| Web: checkout page (sandbox + Razorpay Checkout), plans page, pay buttons on My orders | done | build passes |
| Razorpay live keys, webhook URL registration, Route payouts, GST invoices, boosts/promotion, creator tips | **open** | needs accounts + legal/accounting review |

## Phase 7 checklist
| Item | Status | Evidence |
|---|---|---|
| AI provider adapter (none / Workers AI / Claude), versioned prompt files, gateway: plan quota, budget switch, circuit breaker, call log | done | `tests/test_phase7_ai_calls.py` |
| Caption + hashtag suggestions (user edits), listing assistant, toxic-comment nudge, translation, subtitles | done (rules locally; AI paths need keys) | quota/fallback test |
| Hybrid search (tsvector + pgvector HNSW + RRF), privacy/blocks/owner filter in SQL, DMs never indexed, embedding cache by hash, re-embed backfill | done | `test_hybrid_search_respects_privacy_blocks_and_never_indexes_dms` |
| RAG assistant: help docs + own content + own business data, citations, "I don't know", untrusted-source wrapping, tenant boundary | done | assistant tests + smoke step 22 |
| MCP at /mcp: tokens with scopes, tools (search_posts, get_profile, list_notifications, get_bookings, get_orders, draft_post), draft-only writes, rate limit, audit | done (PAT; OAuth 2.1 open, ADR 0019) | `test_mcp_scopes_drafts_and_auth` + smoke 23–24 |
| LiveKit calls: 5-min tokens after membership/block checks, ringing over WebSocket, 1:1 + small group call page | done | `test_call_tokens_membership_blocks_and_claims` + smoke 25 |
| Real provider keys (Workers AI, Claude, LiveKit Cloud), RAG golden set in CI, spam model, call quality telemetry | **open** | needs accounts / data |

## Phase 8 checklist
| Item | Status | Evidence |
|---|---|---|
| Prometheus metrics (RED per route template, outbox lag, dead letters, queue depth, DB pool, WebSockets), `/metrics` hidden at the gateway | done | `tests/test_metrics.py`; Prometheus targets up |
| Prometheus alert rules (Blueprint 18.1) + provisioned Grafana SLO dashboard (`make monitoring`) | done (local) | 7 rules loaded, dashboard provisioned |
| k6 baseline + in-process hot-path profiler | done | `infra/scripts/load/baseline.js`, `scripts/profile_hot_paths.py` |
| Level 1: pure ASGI middleware, no duplicate access log, fewer booking queries | done | reads p95 1.86 s → 195 ms locally |
| Level 2 readiness: PgBouncer + separate media/AI worker (`--profile scale`), `RSV_API_WORKERS` | ready, off by default | runbook `docs/runbooks/scaling.md` |
| Booking p95 < 300 ms | **open** | local disk fsync bound (5.4 ms/op); re-run on staging SSD |
| Caches, replicas, partitions, Kafka, K8s | **deferred** | triggers in ADR 0020 |

## Verified features
| Feature | Status | Evidence / test | Owner |
|---|---|---|---|
| Authentication | working (local) | 33 backend tests; gateway smoke test | — |
| Admin: audit log, role changes | working (API only) | tests | — |
| Posts/media | working (local) | Phase 3 + 4 tests, smoke | — |
| Feed | working (local) | feed tests, smoke | — |
| Notifications (in-app) | working (local) | tests + smoke | — |
| Search | working (local) | Phase 7 tests, smoke | — |
| RAG assistant | working (local, extractive without provider) | tests, smoke | — |
| Image moderation | not implemented | | |
| MCP | working (local, token auth) | tests, smoke | — |
| Business page + booking | working (local) | 50 backend tests; `infra/scripts/smoke_e2e.sh` | — |
| Admin panel UI | not implemented | | |

## Current blockers
- No hosting accounts (VM, Cloudflare, R2, domain DNS), so there is no staging or public URL.
- An earlier RedStarVibe codebase exists at `../../RedStarVibe` (its Docker stack auto-starts and uses port 8080). Decide whether V4 replaces it or should reuse parts of it (see ADR 0017 note).
- ADR 0016 (branch flow) awaits product-owner confirmation.

## Production metrics
- API p95: n/a · Error rate: n/a · Queue oldest-job age: n/a · DB connection utilization: n/a
- Backup last success: n/a · Restore last tested: 2026-11-16 (local only) · AI cost / active user: n/a
