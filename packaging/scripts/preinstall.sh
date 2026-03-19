#!/usr/bin/env bash
# Pre-install: create system user and data directory.
set -euo pipefail

SERVICE_USER="image-generation-mcp"
DATA_DIR="/var/lib/image-generation-mcp"

if ! getent group "$SERVICE_USER" >/dev/null 2>&1; then
    groupadd --system "$SERVICE_USER"
fi

if ! getent passwd "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --gid "$SERVICE_USER" \
        --home-dir "$DATA_DIR" --no-create-home \
        --shell /usr/sbin/nologin \
        "$SERVICE_USER"
fi

install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$DATA_DIR"
