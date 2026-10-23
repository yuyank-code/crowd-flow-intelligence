#!/usr/bin/env bash
# Checks laptop webcam mode end to end in Docker, using ffmpeg's test picture instead of a physical webcam.
# Needs: Docker, ffmpeg, curl, openssl, python3. Creates .env if missing (test use: run in a clean checkout / CI).
set -euo pipefail
cd "$(dirname "$0")/.."
UI=http://localhost:8080; GW=http://localhost:8888
fail() { echo "FAIL: $*"; docker compose --profile laptop logs --tail=60; exit 1; }
ok()   { echo "ok:   $*"; }
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

./scripts/make-env.sh >/dev/null
KEY=$(grep '^OPERATOR_API_KEY=' .env | cut -d= -f2)
docker compose --profile laptop up --build -d
for i in $(seq 1 45); do curl -fs $UI/health >/dev/null 2>&1 && break; sleep 2; [ "$i" = 45 ] && fail "backend not healthy"; done
ok "stack is up"

TEST_PATTERN=1 ./scripts/webcam/start-webcam.sh >/tmp/webcam.log 2>&1 & FF=$!
trap 'kill $FF 2>/dev/null || true; docker compose --profile laptop down -v >/dev/null 2>&1 || true' EXIT
sleep 8
kill -0 $FF 2>/dev/null && ok "webcam script publishes with the .env credentials" || { cat /tmp/webcam.log; fail "webcam script exited"; }

# publishing without credentials must be refused
if timeout 15 ffmpeg -loglevel error -f lavfi -i testsrc=size=64x64:rate=5 -t 3 -c:v libx264 -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/webcam >/tmp/nopass.log 2>&1; then fail "publish without credentials was accepted"; else ok "publish without credentials refused"; fi

ID=$(curl -fs -X POST $UI/api/cctv/sources -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"name":"Laptop webcam","source_type":"rtsp","endpoint":"rtsp://mediamtx-laptop:8554/webcam","playback_path":"webcam"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
ST=$(curl -fs -X POST $UI/api/cctv/sources/$ID/test -H "X-API-Key: $KEY" | python3 -c "import sys,json;print(json.load(sys.stdin)['status'])")
[ "$ST" = online ] && ok "camera test: online" || fail "camera status $ST"
[ "$(code -X POST $UI/api/cctv/sources/$ID/stream/start -H "X-API-Key: $KEY")" = 200 ] && ok "stream started" || fail "stream start"
URL=$(curl -fs $UI/api/cctv/sources/$ID/playback -H "X-API-Key: $KEY" | python3 -c "import sys,json;print(json.load(sys.stdin)['url'])")
case "$URL" in $GW/webcam/index.m3u8?token=*) ok "playback URL points at the browser-facing gateway";; *) fail "unexpected playback url $URL";; esac
BASE=${URL%%\?*}
[ "$(code $BASE)" = 401 ] && ok "manifest without token: 401" || fail "manifest without token not refused"
[ "$(code "$URL")" = 200 ] && ok "manifest with token: 200" || fail "manifest with token refused"
ffmpeg -loglevel error -y -i "$URL" -t 2 -f null - 2>/tmp/dec.log && ok "2s of video decodes through the token URL" || { cat /tmp/dec.log; fail "decode"; }
curl -fs -X POST $UI/api/cctv/sources/$ID/stream/stop -H "X-API-Key: $KEY" >/dev/null
[ "$(code "$URL")" = 401 ] && ok "after stop the same URL is refused" || fail "stop did not revoke"
echo; echo "Laptop webcam mode verified (with a test picture in place of a physical webcam)."
