#!/usr/bin/env bash
# Creates .env with fresh secrets for camera/laptop mode. Mac / Linux / Git Bash / WSL. Needs openssl.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && { echo ".env already exists - leaving it alone."; exit 0; }
hex() { openssl rand -hex 24; }
cat > .env <<ENV
OPERATOR_API_KEY=$(hex)
CCTV_SECRET_KEY=$(openssl rand -base64 32 | tr '+/' '-_')
PLAYBACK_SIGNING_KEY=$(hex)
MEDIA_GATEWAY_BASE_URL=http://mediamtx-laptop:8888
MEDIA_GATEWAY_PUBLIC_URL=http://localhost:8888
GATEWAY_PUBLISH_USER=webcam
GATEWAY_PUBLISH_PASSWORD=$(hex)
ENV
echo "Created .env. Your operator key (type it into the Cameras tab):"
grep '^OPERATOR_API_KEY=' .env | cut -d= -f2
