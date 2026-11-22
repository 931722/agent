#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if command -v podman >/dev/null 2>&1; then
  podman_cli() { podman "$@"; }
elif [ -x .local-tools/podman/package/podman.pkg/Payload/podman/bin/podman ] || [ -x .local-tools/podman-5.6.2/podman.pkg/Payload/podman/bin/podman ]; then
  podman_cli() { sh scripts/podman-local.sh "$@"; }
else
  echo '請先安裝 Podman 並啟動 podman machine。'; exit 1
fi
podman_cli info >/dev/null
if podman_cli container exists kitchen-agent-hw2; then
  if [ "$(podman_cli inspect --format '{{.State.Running}}' kitchen-agent-hw2)" = true ]; then
    echo '出餐系統已在運作，請開啟 http://127.0.0.1:8000'
    exit 0
  fi
  echo '正在啟動既有的出餐容器，網頁位址為 http://127.0.0.1:8000'
  podman_cli start --attach kitchen-agent-hw2
  exit 0
fi
podman_cli build -t kitchen-agent:hw2 -f Containerfile .
if ! podman_cli volume exists kitchen-agent-data; then
  podman_cli volume create kitchen-agent-data >/dev/null
fi
podman_cli run --rm --name kitchen-agent-hw2 \
  -p 127.0.0.1:8000:8000 \
  -e AGENT_MODE="${AGENT_MODE:-ollama}" \
  -e OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://host.containers.internal:11434}" \
  -e OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:4b}" \
  -e OLLAMA_TIMEOUT="${OLLAMA_TIMEOUT:-120}" \
  -v kitchen-agent-data:/app/data \
  kitchen-agent:hw2
