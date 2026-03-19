#!/usr/bin/env bash
# Pre-remove: stop and disable the service.
set -euo pipefail

if systemctl is-active --quiet image-generation-mcp 2>/dev/null; then
    systemctl stop image-generation-mcp
fi

if systemctl is-enabled --quiet image-generation-mcp 2>/dev/null; then
    systemctl disable image-generation-mcp
fi
