#!/usr/bin/env sh
# Nightly encrypted logical backup to the backup bucket (Blueprint 15.1, Stage 1).
# WAL archiving with wal-g (RPO 5 min) is added when the production VM exists; this script is the nightly full copy.
#
# Requires: docker compose stack running, `age` and `rclone` on the host,
#   BACKUP_AGE_RECIPIENT  age public key (private key kept offline in the password manager)
#   BACKUP_REMOTE         rclone remote path, e.g. r2-backup:redstarvibe-backups-prod
set -eu

: "${BACKUP_AGE_RECIPIENT:?set BACKUP_AGE_RECIPIENT}"
: "${BACKUP_REMOTE:?set BACKUP_REMOTE}"
COMPOSE="${COMPOSE:-docker compose}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="rsv-${STAMP}.dump.age"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

$COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=6' \
  | age -r "$BACKUP_AGE_RECIPIENT" > "$TMP/$FILE"

SIZE="$(wc -c < "$TMP/$FILE")"
if [ "$SIZE" -lt 1024 ]; then
  echo "backup too small ($SIZE bytes); refusing to upload" >&2
  exit 1
fi

rclone copyto "$TMP/$FILE" "$BACKUP_REMOTE/daily/$FILE"
echo "backup ok: $BACKUP_REMOTE/daily/$FILE ($SIZE bytes)"
# Retention (7 daily, 4 weekly, 6 monthly) is enforced by bucket lifecycle rules plus infra/scripts/prune_backups.sh.
