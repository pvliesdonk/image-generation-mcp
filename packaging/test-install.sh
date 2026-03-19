#!/usr/bin/env bash
# Test the .deb package install in a disposable Docker container.
# Usage: ./packaging/test-install.sh dist/image-generation-mcp_*.deb
set -euo pipefail

DEB="${1:?Usage: $0 <path-to-deb>}"

if [ ! -f "$DEB" ]; then
    echo "ERROR: $DEB not found"
    exit 1
fi

ABS_DEB="$(cd "$(dirname "$DEB")" && pwd)/$(basename "$DEB")"

echo "==> Testing install of $ABS_DEB in Debian container..."

docker run --rm -v "$ABS_DEB:/tmp/pkg.deb:ro" debian:bookworm-slim bash -eux -c '
    apt-get update -qq
    apt-get install -y -qq python3 >/dev/null 2>&1

    dpkg -i /tmp/pkg.deb || apt-get install -f -y -qq

    # Verify system user
    getent passwd image-generation-mcp >/dev/null
    echo "OK: user exists"

    # Verify data directory
    test -d /var/lib/image-generation-mcp
    echo "OK: data dir exists"

    # Verify service file
    test -f /etc/systemd/system/image-generation-mcp.service
    echo "OK: service file exists"

    # Verify env file
    test -f /etc/image-generation-mcp/env
    echo "OK: env file exists"

    echo ""
    echo "All checks passed."
'
