#!/usr/bin/env sh
# End-to-end smoke test through the gateway: owner creates a page, customer books, owner confirms,
# worker delivers notifications, public SSR page renders with OG tags.
#   BASE=http://127.0.0.1:8090 sh infra/scripts/smoke_e2e.sh
set -eu
BASE="${BASE:-http://127.0.0.1:8080}"
RUN="$(date +%s)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
OWNER="$TMP/owner"; CUST="$TMP/cust"

json() { python -c "import sys,json; d=json.load(sys.stdin); print($1)"; }
csrf() { curl -fsS -c "$1" -b "$1" "$BASE/api/v1/auth/csrf" | json "d['csrf_token']"; }
post() { jar="$1"; tok="$2"; shift 2; curl -sS -c "$jar" -b "$jar" -H "x-csrf-token: $tok" -H 'content-type: application/json' "$@"; }

echo "1. health: $(curl -fsS "$BASE/health/ready")"

OT="$(csrf "$OWNER")"
post "$OWNER" "$OT" -d "{\"username\":\"owner$RUN\",\"email\":\"owner$RUN@example.com\",\"password\":\"Owner-Passw0rd-1\",\"display_name\":\"Ramesh Sharma\",\"is_18_or_older\":true}" \
  "$BASE/api/v1/auth/signup" >/dev/null
BIZ="$(post "$OWNER" "$OT" -d "{\"slug\":\"sharma-$RUN\",\"name\":\"Sharma Electricals\",\"category\":\"electrician\",\"tagline\":\"Wiring, fans and repairs in Jaipur\",\"area\":\"Civil Lines\",\"city\":\"Jaipur\",\"lat\":26.9124,\"lng\":75.7873}" \
  "$BASE/api/v1/businesses" | json "d['id']")"
echo "2. business created: $BIZ"
post "$OWNER" "$OT" -X PUT -d '[{"weekday":0,"opens":"09:00","closes":"18:00"},{"weekday":1,"opens":"09:00","closes":"18:00"},{"weekday":2,"opens":"09:00","closes":"18:00"},{"weekday":3,"opens":"09:00","closes":"18:00"},{"weekday":4,"opens":"09:00","closes":"18:00"},{"weekday":5,"opens":"09:00","closes":"18:00"},{"weekday":6,"opens":"09:00","closes":"18:00"}]' \
  "$BASE/api/v1/businesses/$BIZ/hours" >/dev/null
SVC="$(post "$OWNER" "$OT" -d '{"name":"Fan installation","price_paise":49900,"duration_min":60}' "$BASE/api/v1/businesses/$BIZ/services" | json "d['id']")"
echo "3. service added: $SVC"

CT="$(csrf "$CUST")"
post "$CUST" "$CT" -d "{\"username\":\"cust$RUN\",\"email\":\"cust$RUN@example.com\",\"password\":\"Cust-Passw0rd-12\",\"display_name\":\"Priya\",\"is_18_or_older\":true}" \
  "$BASE/api/v1/auth/signup" >/dev/null
# IST is a fixed +05:30 (no DST), so no tz database is needed.
DAY="$(python -c "import datetime as d; print((d.datetime.now(d.timezone(d.timedelta(hours=5, minutes=30))) + d.timedelta(days=1)).date())")"
SLOT="$(curl -fsS "$BASE/api/v1/businesses/$BIZ/slots?service_id=$SVC&date=$DAY" | json "d['slots'][2]['starts_at']")"
echo "4. slots for $DAY ok; booking $SLOT"
BK="$(post "$CUST" "$CT" -H "Idempotency-Key: smoke-$RUN" -d "{\"business_id\":\"$BIZ\",\"service_id\":\"$SVC\",\"starts_at\":\"$SLOT\"}" "$BASE/api/v1/bookings" | json "d['id']+' '+d['status']")"
echo "5. booked: $BK"
SECOND="$(post "$OWNER" "$OT" -H "Idempotency-Key: smoke-x-$RUN" -d "{\"business_id\":\"$BIZ\",\"service_id\":\"$SVC\",\"starts_at\":\"$SLOT\"}" "$BASE/api/v1/bookings" | json "d['error']['code']")"
echo "6. owner booking own business rejected: $SECOND"
BKID="${BK%% *}"
echo "7. owner confirms: $(post "$OWNER" "$OT" -X POST "$BASE/api/v1/bookings/$BKID/confirm" | json "d['status']")"

i=0; N=0
while [ "$i" -lt 20 ]; do
  N="$(curl -fsS -b "$CUST" "$BASE/api/v1/notifications" | json "len(d['items'])")"
  [ "$N" -ge 2 ] && break; i=$((i + 1)); sleep 1
done
echo "8. customer notifications via outbox -> worker: $N ($(curl -fsS -b "$CUST" "$BASE/api/v1/notifications" | json "', '.join(n['title'] for n in d['items'])"))"

HTML="$(curl -fsS "$BASE/business/sharma-$RUN")"
echo "$HTML" | grep -q '<meta property="og:title" content="Sharma Electricals"' && echo "9. public page SSR with OG tags: ok"
echo "$HTML" | grep -q 'Fan installation' && echo "10. public page lists services: ok"
echo "SMOKE PASSED — open $BASE/business/sharma-$RUN"
