#!/usr/bin/env bash
# Post-install: reload systemd, create default env file, print instructions.
set -euo pipefail

CONFIG_DIR="/etc/image-generation-mcp"
ENV_FILE="$CONFIG_DIR/env"
EXAMPLE_FILE="$CONFIG_DIR/env.example"

systemctl daemon-reload

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
