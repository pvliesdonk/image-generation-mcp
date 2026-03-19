#!/usr/bin/env bash
# Post-remove: reload systemd units.
# Does NOT remove user or data directory — that is the operator's choice.
set -euo pipefail

systemctl daemon-reload 2>/dev/null || true
