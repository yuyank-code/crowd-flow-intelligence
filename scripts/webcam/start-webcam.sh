#!/usr/bin/env bash
# Sends this computer's webcam to the CrowdFlow gateway (macOS and Linux). Needs ffmpeg and the repo's .env.
# Usage: ./scripts/webcam/start-webcam.sh [device]     (macOS: index like 0; Linux: /dev/video0)
# Stop with Ctrl+C. TEST_PATTERN=1 sends a test picture instead of the webcam.
set -euo pipefail
cd "$(dirname "$0")/../.."
command -v ffmpeg >/dev/null || { echo "ffmpeg not found. macOS: brew install ffmpeg   Ubuntu/Debian: sudo apt install ffmpeg"; exit 1; }
[ -f .env ] || { echo "No .env found. Run ./scripts/make-env.sh first."; exit 1; }
envval() { grep "^$1=" .env | head -1 | cut -d= -f2-; }
URL="${RTSP_URL:-rtsp://$(envval GATEWAY_PUBLISH_USER):$(envval GATEWAY_PUBLISH_PASSWORD)@127.0.0.1:8554/webcam}"
OUT=(-c:v libx264 -preset ultrafast -tune zerolatency -g 15 -pix_fmt yuv420p -f rtsp -rtsp_transport tcp "$URL")
if [ "${TEST_PATTERN:-0}" = 1 ]; then
  exec ffmpeg -re -f lavfi -i "testsrc=size=640x480:rate=15" "${OUT[@]}"
fi
case "$(uname -s)" in
  Darwin)
    DEV="${1:-0}"
    echo "Using camera $DEV. If this fails, list cameras with:  ffmpeg -f avfoundation -list_devices true -i \"\""
    echo "macOS may ask permission for your terminal to use the camera - click Allow."
    exec ffmpeg -f avfoundation -framerate 30 -i "$DEV" "${OUT[@]}" ;;
  Linux)
    DEV="${1:-/dev/video0}"
    echo "Using camera $DEV"
    exec ffmpeg -f v4l2 -framerate 15 -video_size 640x480 -i "$DEV" "${OUT[@]}" ;;
  *) echo "On Windows use scripts\\webcam\\start-webcam.ps1"; exit 1 ;;
esac
