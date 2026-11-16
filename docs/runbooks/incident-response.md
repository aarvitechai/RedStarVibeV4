# Runbook: incident response

## Severity
| Sev | Example | Response |
|---|---|---|
| P1 | site down, data loss, security breach, payments wrong | page on-call now; status update every 30 min |
| P2 | a core flow broken (signup, booking) for some users | fix or mitigate within 4 h |
| P3 | degraded feature with a workaround | next working day |

## First 15 minutes
1. Acknowledge the alert; name an incident lead.
2. Check `/health/ready`, Grafana (5xx, p95, queue age, DB connections), Sentry (new errors by release).
3. Mitigate first: roll back the last deploy, disable the feature flag, or set `RSV_AI_PROVIDER=none`.
4. Security incident: rotate affected secrets, revoke sessions (`UPDATE accounts.sessions SET revoked_at = now()` for affected users), preserve logs.

## Useful commands (on the VM)
```
docker compose ps
docker compose logs --since 15m api worker beat
docker compose exec db psql -U rsv -d rsv -c "select count(*) from notify.outbox where published_at is null"
docker compose exec db psql -U rsv -d rsv -c "select type, error, created_at from notify.dead_letter order by id desc limit 20"
```

## After
Write a blameless report within 48 h: timeline, impact, root cause, RPO/RTO if data was involved, and follow-up issues. India DPDP Act: a personal-data breach must be reported — involve legal immediately.
