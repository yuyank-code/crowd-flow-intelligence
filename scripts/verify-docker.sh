#!/usr/bin/env bash
# Builds and starts the stack, then checks it end to end through the nginx proxy.
# Usage: ./scripts/verify-docker.sh      (from the repo root; Docker must be running)
set -euo pipefail
export OPERATOR_API_KEY="${OPERATOR_API_KEY:-$(openssl rand -hex 24)}"
UI=http://localhost:8080
fail() { echo "FAIL: $*"; docker compose logs --tail=40; exit 1; }
ok()   { echo "ok:   $*"; }

docker compose up --build -d
for i in $(seq 1 40); do
  curl -fs $UI/health >/dev/null 2>&1 && break
  sleep 2; [ "$i" = 40 ] && fail "backend not healthy via nginx after 80s"
done
ok "UI served and /health proxied"
curl -fs $UI/ | grep -qi "<div id=\"root\"" && ok "frontend index.html served" || fail "index.html missing root div"
curl -fs $UI/api/simulation | grep -q '"nodes"' && ok "GET /api/simulation via proxy" || fail "api proxy"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST $UI/api/simulation/start)
[ "$code" = 401 ] && ok "start without key -> 401" || fail "expected 401, got $code"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "X-API-Key: $OPERATOR_API_KEY" $UI/api/simulation/start)
[ "$code" = 200 ] && ok "start with key -> 200" || fail "expected 200, got $code"
docker compose exec -T backend python - <<'PY' && ok "WebSocket streams through backend" || fail "websocket"
import asyncio, json, websockets
async def main():
    async with websockets.connect("ws://localhost:8000/ws/simulation") as ws:
        assert "state" in json.loads(await ws.recv())
asyncio.run(main())
PY
curl -s -o /dev/null -w '' -H "Origin: http://localhost:8080" $UI/api/simulation
docker compose restart backend >/dev/null
sleep 6
curl -fs "$UI/api/simulation/history?limit=1" >/dev/null && ok "history endpoint works after restart (volume persisted)" || fail "history after restart"
echo; echo "All checks passed. Open $UI  (operator key: $OPERATOR_API_KEY)"
