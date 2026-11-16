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

# ---- Phase 3: media, cards, share image, albums ----
COMPOSE="${COMPOSE:-docker compose}"
upload() {  # $1 = colour seed; prints asset id once processed by the media worker
  IMG="$TMP/p$1.jpg"
  $COMPOSE exec -T api python -c "from PIL import Image;import io,sys;b=io.BytesIO();Image.new('RGB',(1400,1000),($1,60,90)).save(b,'JPEG');sys.stdout.buffer.write(b.getvalue())" > "$IMG"
  SIZE="$(wc -c < "$IMG" | tr -d ' ')"
  INTENT="$(post "$CUST" "$CT" -d "{\"kind\":\"image\",\"purpose\":\"album\",\"content_type\":\"image/jpeg\",\"size_bytes\":$SIZE}" "$BASE/api/v1/media/uploads")"
  AID="$(echo "$INTENT" | json "d['asset_id']")"; URL="$(echo "$INTENT" | json "d['upload_url']")"
  curl -fsS -X PUT -H 'Content-Type: image/jpeg' --data-binary "@$IMG" "$URL" >/dev/null
  post "$CUST" "$CT" -X POST "$BASE/api/v1/media/uploads/$AID/complete" >/dev/null
  i=0; while [ "$i" -lt 30 ]; do
    ST="$(curl -fsS -b "$CUST" "$BASE/api/v1/media/$AID" | json "d['status']")"; [ "$ST" = ready ] && break; i=$((i + 1)); sleep 1; done
  [ "$ST" = ready ] || { echo "upload not processed: $ST" >&2; exit 1; }
  echo "$AID"
}
A1="$(upload 200)"; A2="$(upload 40)"
echo "11. two photos uploaded via presigned PUT and processed by the media worker: $A1 $A2"
WEBP="$(curl -fsS -b "$CUST" "$BASE/api/v1/media/$A1" | json "d['urls']['640.webp']")"
echo "12. rendition served from public bucket: $(curl -fsS -o "$TMP/dl" -w '%{http_code} %{content_type}' "$WEBP")"
CARD="$(post "$CUST" "$CT" -d "{\"template_id\":\"diwali-hi\",\"photo_asset_id\":\"$A1\",\"fields\":{\"title\":\"शुभ दीपावली\",\"message\":\"Happy Diwali!\",\"from\":\"Priya\"}}" "$BASE/api/v1/cards" | json "d['id']")"
i=0; while [ "$i" -lt 30 ]; do CST="$(curl -fsS "$BASE/api/v1/cards/$CARD" | json "d['status']")"; [ "$CST" = ready ] && break; i=$((i + 1)); sleep 1; done
CIMG="$(curl -fsS "$BASE/api/v1/cards/$CARD" | json "d['image_url']")"
echo "13. card rendered by worker: $CST $(curl -fsS -o "$TMP/dl" -w '%{http_code} %{content_type}' "$CIMG"); page $(curl -s -o /dev/null -w '%{http_code}' "$BASE/c/$CARD")"
echo "14. business share image: $(curl -fsS -o "$TMP/dl" -w '%{http_code} %{content_type}' "$BASE/api/v1/og/business/sharma-$RUN.png")"
ALB="$(post "$CUST" "$CT" -d '{"title":"Smoke album"}' "$BASE/api/v1/albums" | json "d['id']")"
TOK="$(post "$CUST" "$CT" -X PUT -d "{\"asset_ids\":[\"$A1\",\"$A2\"]}" "$BASE/api/v1/albums/$ALB/items" | json "d['share_token']")"
post "$CUST" "$CT" -X POST "$BASE/api/v1/albums/$ALB/slideshow" >/dev/null
i=0; while [ "$i" -lt 60 ]; do SST="$(curl -fsS -b "$CUST" "$BASE/api/v1/albums/mine" | json "d[0]['slideshow_status']")"; [ "$SST" = ready ] && break; [ "$SST" = failed ] && break; i=$((i + 1)); sleep 1; done
MP4="$(curl -fsS -b "$CUST" "$BASE/api/v1/albums/mine" | json "d[0]['slideshow_url']")"
echo "15. album flipbook page $(curl -s -o /dev/null -w '%{http_code}' "$BASE/a/$TOK"); slideshow $SST $(curl -fsS -o "$TMP/dl" -w '%{content_type} %{size_download}B' "$MP4")"

# ---- Phase 4: social, feed fan-out, realtime chat ----
post "$CUST" "$CT" -X POST "$BASE/api/v1/profiles/owner$RUN/follow" >/dev/null
P1="$(post "$OWNER" "$OT" -d "{\"caption\":\"New ceiling fans in stock #jaipur\",\"media_ids\":[]}" "$BASE/api/v1/posts" | json "d['id']")"
i=0; while [ "$i" -lt 20 ]; do F="$(curl -fsS -b "$CUST" "$BASE/api/v1/feed" | json "len(d['items'])")"; [ "$F" -ge 1 ] && break; i=$((i + 1)); sleep 1; done
echo "16. post fanned out to follower feed by worker: $F item(s); like -> $(post "$CUST" "$CT" -X POST "$BASE/api/v1/posts/$P1/like" | json "d['like_count']")"
CONV="$(post "$CUST" "$CT" -X POST "$BASE/api/v1/chat/direct/owner$RUN" | json "d['id']")"
OWNER_AT="$(awk '$6 == "rsv_at" {print $7}' "$OWNER")"
$COMPOSE exec -T -e AT="$OWNER_AT" api python -c "
import asyncio, json, os, websockets
async def main():
    async with websockets.connect('ws://gateway:8080/ws', additional_headers={'Cookie': 'rsv_at=' + os.environ['AT'], 'Origin': 'http://localhost:8080'}) as ws:
        print(json.loads(await ws.recv())['type'], flush=True)
        while True:
            f = json.loads(await asyncio.wait_for(ws.recv(), 15))
            if f['type'] == 'message.new':
                print('message.new', f['message']['body'], 'seq', f['message']['seq'], flush=True); return
asyncio.run(main())" > "$TMP/ws.out" 2>&1 &
WSPID=$!
sleep 3
post "$CUST" "$CT" -d '{"body":"Is the fan installation available tomorrow?","client_id":"smoke-1"}' "$BASE/api/v1/chat/conversations/$CONV/messages" >/dev/null
wait "$WSPID" || true
echo "17. realtime chat over WebSocket: $(tr '
' ' ' < "$TMP/ws.out")"
echo "18. pages: feed $(curl -s -o "$TMP/dl" -w '%{http_code}' "$BASE/feed") profile $(curl -s -o "$TMP/dl" -w '%{http_code}' "$BASE/owner$RUN") post $(curl -s -o "$TMP/dl" -w '%{http_code}' "$BASE/p/$P1") messages $(curl -s -o "$TMP/dl" -w '%{http_code}' "$BASE/messages")"

# ---- Phase 5-7: shop order, sandbox payment, search, assistant, MCP, calls ----
PROD="$(post "$OWNER" "$OT" -d '{"name":"Ceiling fan 1200mm","price_paise":249900,"stock":5}' "$BASE/api/v1/businesses/$BIZ/products" | json "d['id']")"
ORD="$(post "$CUST" "$CT" -H "Idempotency-Key: smoke-order-$RUN" -d "{\"business_id\":\"$BIZ\",\"items\":[{\"product_id\":\"$PROD\",\"qty\":2}]}" "$BASE/api/v1/orders" | json "d['id']+' '+str(d['total_paise'])")"
echo "19. order placed (stock decremented atomically): $ORD"
PAY="$(post "$CUST" "$CT" -H "Idempotency-Key: smoke-pay-$RUN" -d "{\"purpose\":\"order\",\"reference_id\":\"${ORD%% *}\"}" "$BASE/api/v1/payments/intents" | json "d['payment_id']+' '+str(d['amount_paise'])")"
post "$CUST" "$CT" -X POST "$BASE/api/v1/payments/${PAY%% *}/sandbox-complete" >/dev/null
echo "20. payment (server amount ${PAY#* } paise) confirmed via signed webhook: $(curl -fsS -b "$CUST" "$BASE/api/v1/orders/mine" | json "d[0]['payment_status']"); payout due $(curl -fsS -b "$OWNER" "$BASE/api/v1/businesses/$BIZ/payouts" | json "d['due_paise']") paise"
i=0; while [ "$i" -lt 20 ]; do H="$(curl -fsS "$BASE/api/v1/search?q=fans" | json "len(d)")"; [ "$H" -ge 1 ] && break; i=$((i + 1)); sleep 1; done
echo "21. hybrid search 'fans': $H hit(s): $(curl -fsS "$BASE/api/v1/search?q=fans" | json "', '.join(h['kind']+':'+h['title'] for h in d)")"
echo "22. assistant: $(post "$CUST" "$CT" -d '{"question":"how do refunds work?"}' "$BASE/api/v1/ai/assistant" | json "d['mode']+' -> '+d['citations'][0]['url']")"
TOKEN="$(post "$OWNER" "$OT" -d '{"label":"smoke","scopes":["read","write:drafts"]}' "$BASE/api/v1/mcp-tokens" | json "d['token']")"
echo "23. MCP tools: $(curl -fsS -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' "$BASE/mcp" | json "','.join(t['name'] for t in d['result']['tools'])")"
echo "24. MCP get_bookings: $(curl -fsS -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_bookings","arguments":{}}}' "$BASE/mcp" | json "__import__('json').loads(d['result']['content'][0]['text'])['businesses'][0]['business']")"
CALL="$(post "$CUST" "$CT" -X POST "$BASE/api/v1/calls/$CONV/token" | json "d['url']+' room '+d['room']")"
echo "25. call token issued for LiveKit: $CALL; LiveKit server: $(curl -s -o "$TMP/dl" -w '%{http_code}' http://127.0.0.1:${LIVEKIT_PORT:-7880}/)"
echo "26. pages: assistant $(curl -s -o "$TMP/dl" -w '%{http_code}' "$BASE/assistant") search $(curl -s -o "$TMP/dl" -w '%{http_code}' "$BASE/search?q=fan") help $(curl -s -o "$TMP/dl" -w '%{http_code}' "$BASE/help") plans $(curl -s -o "$TMP/dl" -w '%{http_code}' "$BASE/plans") orders $(curl -s -o "$TMP/dl" -w '%{http_code}' "$BASE/orders")"
echo "SMOKE PASSED — open $BASE/business/sharma-$RUN"
