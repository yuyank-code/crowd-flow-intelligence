#!/usr/bin/env bash
# Real-gateway check of the playback-token flow: MediaMTX + ffmpeg test pattern + this backend (no real camera needed).
# Needs: MEDIAMTX_BIN, ffmpeg, curl, python deps installed. Every line should match its "(expect ...)" note.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
MTX="${MEDIAMTX_BIN:?set MEDIAMTX_BIN to a MediaMTX v1.12.x binary (https://github.com/bluenviron/mediamtx/releases)}"
export OPERATOR_API_KEY=opkey CCTV_ALLOW_LOOPBACK=true PLAYBACK_SIGNING_KEY=signkey PLAYBACK_TOKEN_TTL_SEC=6
export CCTV_SECRET_KEY=$(python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())")
export MEDIA_GATEWAY_BASE_URL=http://127.0.0.1:18888 DATABASE_URL=sqlite+aiosqlite:////tmp/e2e.db
rm -f /tmp/e2e.db
$MTX $REPO/infra/mediamtx/mediamtx.test.yml >/tmp/e2e_mtx.log 2>&1 & MP=$!
python -m uvicorn app.main:app --app-dir $REPO/backend --port 18000 >/tmp/e2e_api.log 2>&1 & AP=$!
sleep 4
ffmpeg -loglevel error -re -f lavfi -i testsrc=size=320x240:rate=10 -c:v libx264 -preset ultrafast -tune zerolatency -g 10 -pix_fmt yuv420p -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:18554/cam1 >/tmp/e2e_ff.log 2>&1 & FP=$!
sleep 6
API=http://127.0.0.1:18000/api/cctv; H="X-API-Key: opkey"
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
ID=$(curl -s -X POST $API/sources -H "$H" -H 'Content-Type: application/json' -d '{"name":"E2E cam","source_type":"rtsp","endpoint":"rtsp://127.0.0.1:18554/cam1","playback_path":"cam1"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "camera id: $ID"
echo "test connection: $(curl -s -X POST $API/sources/$ID/test -H "$H" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'], d.get('diagnostic'))")"
echo "start stream: $(code -X POST $API/sources/$ID/stream/start -H "$H")  (expect 200)"
URL=$(curl -s $API/sources/$ID/playback -H "$H" | python3 -c "import sys,json;print(json.load(sys.stdin)['url'])")
BASE=${URL%%\?*}; TOK=${URL##*token=}; DIR=${BASE%/*}
echo "manifest, no token:       $(code $BASE)  (expect 401)"
echo "manifest, bad token:      $(code "$BASE?token=1.abc")  (expect 401)"
echo "manifest, valid token:    $(code "$BASE?token=$TOK")  (expect 200)"
curl -s "$BASE?token=$TOK" | head -8
VARIANT=$(curl -s "$BASE?token=$TOK" | grep '\.m3u8' | grep -v '^#' | head -1 | sed 's/?token=.*//')
echo "variant playlist: $VARIANT"
curl -s "$DIR/$VARIANT" >/dev/null; echo "variant, no token:        $(code "$DIR/$VARIANT")  (expect 401)"
curl -s "$DIR/${VARIANT}?token=$TOK" > /tmp/e2e_var.m3u8; echo "variant, valid token:     $(code "$DIR/${VARIANT}?token=$TOK")  (expect 200)"
sleep 2; curl -s "$DIR/${VARIANT}?token=$TOK" > /tmp/e2e_var.m3u8; head -12 /tmp/e2e_var.m3u8
SEG=$(grep -v '^#' /tmp/e2e_var.m3u8 | grep . | head -1 | sed 's/?token=.*//')
echo "segment: $SEG"
echo "segment, no token:        $(code "$DIR/$SEG")  (expect 401)"
echo "segment, valid token:     $(code "$DIR/${SEG}?token=$TOK")  (expect 200)"
ffmpeg -loglevel error -y -i "$BASE?token=$TOK" -t 2 -f null - 2>/tmp/e2e_dec.log && echo "decode 2s of video via token URL: ok  (expect ok)" || echo "decode via token URL: FAILED $(head -2 /tmp/e2e_dec.log)"
echo "publish w/o auth exclude is test-only; api/metrics ports closed: $(code http://127.0.0.1:9997/v3/paths/list) (expect 000)"
echo "direct POST hook, wrong action: $(code -X POST $API/gateway/auth -H 'Content-Type: application/json' -d '{"action":"publish","protocol":"rtsp","path":"cam1"}') (expect 401)"
sleep 8
echo "after TTL, same token:    $(code "$BASE?token=$TOK")  (expect 401, TTL=6s)"
NEW=$(curl -s $API/sources/$ID/playback -H "$H" | python3 -c "import sys,json;print(json.load(sys.stdin)['url'])")
echo "renewed token:            $(code "$NEW")  (expect 200)"
curl -s -X POST $API/sources/$ID/stream/stop -H "$H" >/dev/null
echo "after stop, fresh token blocked: $(code "$NEW")  (expect 401)"
kill $FP $MP $AP 2>/dev/null; wait 2>/dev/null; true
