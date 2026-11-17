#!/usr/bin/env sh
# Temporary public test link for the LOCAL stack via a Cloudflare quick tunnel (random *.trycloudflare.com URL).
# Testing only: no uptime guarantee, the URL changes on every start, and your machine serves the traffic.
#
#   sh infra/scripts/public_tunnel.sh          start (or restart) and print the URL
#   sh infra/scripts/public_tunnel.sh stop     stop the tunnel and point the app back to localhost
set -eu

PROJECT="${PROJECT:-rsv4}"
COMPOSE="docker compose -p $PROJECT"
NAME="$PROJECT-tunnel"
cd "$(dirname "$0")/../.."

set_env() {  # set_env KEY VALUE  (replace or append in .env)
  if grep -q "^$1=" .env; then sed -i "s#^$1=.*#$1=$2#" .env; else printf '%s=%s\n' "$1" "$2" >> .env; fi
}

restart_app() {
  $COMPOSE up -d --force-recreate --no-deps api ws worker beat web >/dev/null
  $COMPOSE restart gateway >/dev/null
}

if [ "${1:-}" = "stop" ]; then
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  PORT="$(grep '^RSV_HTTP_PORT=' .env | cut -d= -f2)"; PORT="${PORT:-8080}"
  set_env RSV_PUBLIC_BASE_URL "http://localhost:$PORT"
  set_env RSV_S3_PRESIGN_ENDPOINT "http://localhost:$PORT"
  set_env RSV_MEDIA_PUBLIC_BASE "http://localhost:$PORT/rsv-public"
  restart_app
  echo "Tunnel stopped; app is local-only again at http://localhost:$PORT"
  exit 0
fi

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --network "${PROJECT}_public" --restart unless-stopped \
  cloudflare/cloudflared:2025.10.0 tunnel --no-autoupdate --url http://gateway:8080 >/dev/null

URL=""
i=0
while [ -z "$URL" ] && [ "$i" -lt 45 ]; do
  URL="$(docker logs "$NAME" 2>&1 | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1 || true)"
  i=$((i + 1)); sleep 2
done
[ -n "$URL" ] || { echo "Tunnel did not start; see: docker logs $NAME" >&2; exit 1; }

# The app builds links, presigned upload URLs and the WebSocket origin check from these.
set_env RSV_PUBLIC_BASE_URL "$URL"
set_env RSV_S3_PRESIGN_ENDPOINT "$URL"
set_env RSV_MEDIA_PUBLIC_BASE "$URL/rsv-public"
set_env RSV_RATE_LIMIT_SIGNUP_PER_HOUR 30   # public link: keep abuse limits close to production
restart_app

i=0
until curl -fsS "$URL/health/ready" >/dev/null 2>&1 || [ "$i" -ge 30 ]; do i=$((i + 1)); sleep 2; done
echo ""
echo "Public test URL: $URL"
echo "Stop it with:    sh infra/scripts/public_tunnel.sh stop"
