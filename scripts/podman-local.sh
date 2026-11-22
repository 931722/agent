#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
# Cloned repositories use a normal system installation. The portable
# tools and Disk paths below apply only to the original development machine.
if [ ! -d "$project_root/.local-tools/podman-5.6.2" ] && [ ! -d "$project_root/.local-tools/podman" ]; then
  if command -v podman >/dev/null 2>&1; then
    exec podman "$@"
  fi
  echo '請先安裝 podman，並依 README 啟動服務。' >&2
  exit 1
fi

if [ ! -d /Volumes/Disk/file/Podman/data ] || [ ! -w /Volumes/Disk/file/Podman/data ] || [ ! -d /Volumes/Disk/file/Podman/config ]; then
  echo '找不到 Disk 磁碟上的 Podman 資料，或無法寫入。請先接上 Disk；不會建立新的本機虛擬機。' >&2
  exit 1
fi
if [ -x "$project_root/.local-tools/podman-5.6.2/podman.pkg/Payload/podman/bin/podman" ]; then
  export CONTAINERS_CONF="$project_root/.local-tools/containers-5.6.conf"
  exec "$project_root/.local-tools/podman-5.6.2/podman.pkg/Payload/podman/bin/podman" "$@"
fi
export CONTAINERS_CONF="$project_root/.local-tools/containers.conf"
exec "$project_root/.local-tools/podman/package/podman.pkg/Payload/podman/bin/podman" "$@"
