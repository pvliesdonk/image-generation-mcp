#!/usr/bin/env bash
# Post-install: reload systemd, install uv, create default env file, print instructions.
set -euo pipefail

CONFIG_DIR="/etc/image-generation-mcp"
ENV_FILE="$CONFIG_DIR/env"
EXAMPLE_FILE="$CONFIG_DIR/env.example"

systemctl daemon-reload

# Install uv if not already present
if ! command -v uvx >/dev/null 2>&1; then
    echo "  Installing uv (required for image-generation-mcp)..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh >/dev/null 2>&1
    else
        echo "  WARNING: curl not found — install uv manually:"
        echo "    curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh"
    fi
fi

# Copy example env if no env file exists yet
if [ ! -f "$ENV_FILE" ] && [ -f "$EXAMPLE_FILE" ]; then
    cp "$EXAMPLE_FILE" "$ENV_FILE"
    chmod 0640 "$ENV_FILE"
    chown root:image-generation-mcp "$ENV_FILE"
fi

echo ""
echo "  image-generation-mcp installed successfully."
echo ""
echo "  Next steps:"
echo "    1. Edit /etc/image-generation-mcp/env"
echo "    2. sudo systemctl enable --now image-generation-mcp"
echo "    3. sudo journalctl -u image-generation-mcp -f"
echo ""
