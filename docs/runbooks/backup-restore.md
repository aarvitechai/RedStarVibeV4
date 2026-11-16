# Runbook: backup and restore

**Rule:** a backup that was never restored is not a backup. The monthly drill is a release blocker if it fails.

## Nightly backup
- Script: `infra/scripts/backup.sh` (cron on the VM at 02:30 IST). Output: encrypted `pg_dump` in `$BACKUP_REMOTE/daily/`.
- Encryption: `age` public key on the server; the private key lives only in the team password manager (offline copy).
- Retention: 7 daily, 4 weekly, 6 monthly (bucket lifecycle rules).
- Alert: the cron wrapper posts failure to the alert channel; Grafana alerts if no backup in 26 h.
- Stage 1 next step: wal-g WAL archiving to a separate R2 bucket for RPO ≤ 5 min.

## Monthly restore drill
1. Pick the latest backup and note its timestamp.
2. `AGE_IDENTITY=~/keys/backup.agekey infra/scripts/restore_drill.sh <file>`
3. The script restores into a throwaway container, checks migration version, row counts and session/user integrity, and prints the time taken.
4. Record the result below. If it fails, open a P1 issue.

To test the drill mechanics locally: `infra/scripts/restore_drill.sh --local`.

## Drill log
| Date | Backup | Result | Time (RTO) | Notes |
|---|---|---|---|---|
| 2026-11-16 | local stack (`--local`) | PASSED | 16 s | migration 0002, 1 user, integrity OK. Not a production RTO: real data volumes will take longer. |

## Real restore (incident)
1. Declare an incident (`incident-response.md`). Stop writes: scale `api`, `worker`, `beat` to 0.
2. Restore into a new database (never over the broken one); verify with the drill checks.
3. Point `RSV_DATABASE_URL` at it, run `migrate`, start services, run smoke tests.
4. Record data-loss window (RPO) and time taken (RTO) in the incident report.
