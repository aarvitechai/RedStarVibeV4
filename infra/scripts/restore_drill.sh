#!/usr/bin/env sh
# Restore drill (monthly, release blocker if it fails). Restores a backup into a throwaway container,
# runs integrity checks and prints the time taken (RTO). Never touches the running database.
#
#   restore_drill.sh path/to/rsv-YYYYmmddTHHMMSSZ.dump.age   (needs AGE_IDENTITY=path/to/private-key)
#   restore_drill.sh --local                                  (dumps the local stack first; for testing the drill itself)
set -eu

COMPOSE="${COMPOSE:-docker compose}"
IMAGE="${RESTORE_IMAGE:-redstarvibe-postgres:16}"
NAME="rsv-restore-drill-$$"
TMP="$(mktemp -d)"
START="$(date +%s)"
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT

if [ "${1:-}" = "--local" ]; then
  $COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$TMP/backup.dump"
else
  : "${1:?usage: restore_drill.sh <backup.dump.age> | --local}"
  : "${AGE_IDENTITY:?set AGE_IDENTITY to the backup private key file}"
  age -d -i "$AGE_IDENTITY" "$1" > "$TMP/backup.dump"
fi

docker run -d --name "$NAME" -e POSTGRES_PASSWORD=drill -e POSTGRES_USER=rsv -e POSTGRES_DB=rsv "$IMAGE" >/dev/null
i=0
until docker exec "$NAME" pg_isready -U rsv -d rsv >/dev/null 2>&1; do
  i=$((i + 1)); [ "$i" -gt 60 ] && { echo "restore DB did not start" >&2; exit 1; }; sleep 1
done
sleep 2

docker cp "$TMP/backup.dump" "$NAME:/tmp/backup.dump"
docker exec "$NAME" pg_restore -U rsv -d rsv --no-owner --exit-on-error /tmp/backup.dump

q() { docker exec "$NAME" psql -U rsv -d rsv -tAc "$1"; }
echo "migration version: $(q 'select version_num from alembic_version')"
echo "users:             $(q 'select count(*) from accounts.users')"
echo "audit entries:     $(q 'select count(*) from accounts.audit_log')"
echo "pending outbox:    $(q 'select count(*) from notify.outbox where published_at is null')"
# Integrity: every session belongs to an existing user.
ORPHANS="$(q 'select count(*) from accounts.sessions s left join accounts.users u on u.id = s.user_id where u.id is null')"
[ "$ORPHANS" = "0" ] || { echo "integrity check failed: $ORPHANS orphan sessions" >&2; exit 1; }

echo "RESTORE DRILL PASSED in $(( $(date +%s) - START )) s — record this in docs/runbooks/backup-restore.md"
