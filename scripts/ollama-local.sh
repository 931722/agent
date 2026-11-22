#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
# Cloned repositories use a normal system installation. The portable
# tools and Disk paths below apply only to the original development machine.
if [ ! -d "$project_root/.local-tools/ollama" ]; then
  if command -v ollama >/dev/null 2>&1; then
    exec ollama "$@"
  fi
  echo '請先安裝 ollama，並依 README 啟動服務。' >&2
  exit 1
fi

export OLLAMA_MODELS="/Volumes/Disk/file/Ollama/models"
if [ ! -d "$OLLAMA_MODELS" ] || [ ! -w "$OLLAMA_MODELS" ]; then
  echo '找不到 Disk 磁碟上的模型資料夾，或無法寫入。請先接上 Disk；不會改用本機磁碟。' >&2
  exit 1
fi
exec "$project_root/.local-tools/ollama/ollama" "$@"
