#!/usr/bin/env bash
# rename.sh — bootstrap a new MCP server from this template.
#
# Usage:
#   ./scripts/rename.sh <repo-name> <python_module> <ENV_PREFIX> "Human Name"
#
# Example:
#   ./scripts/rename.sh my-weather-service my_weather_service WEATHER_MCP "Weather MCP Server"
#
# What it replaces (case-sensitive, across all text files):
#   image-gen-mcp  → <repo-name>
#   image_gen_mcp  → <python_module>
#   IMAGE_GEN_MCP               → <ENV_PREFIX>
#   Image Gen MCP Server  → <Human Name>
#   image-gen-mcp               → <repo-name>  (CLI command)
#
# Safe to run multiple times (idempotent after first run).

set -euo pipefail

if [ "$#" -ne 4 ]; then
    echo "Usage: $0 <repo-name> <python_module> <ENV_PREFIX> \"Human Name\""
    echo "Example: $0 my-weather-service my_weather_service WEATHER_MCP \"Weather MCP Server\""
    exit 1
fi

REPO_NAME="$1"
PYTHON_MODULE="$2"
ENV_PREFIX="$3"
HUMAN_NAME="$4"
CLI_CMD="$REPO_NAME"

echo "Renaming template:"
echo "  repo name    : image-gen-mcp → $REPO_NAME"
echo "  python module: image_gen_mcp → $PYTHON_MODULE"
echo "  env prefix   : IMAGE_GEN_MCP → $ENV_PREFIX"
echo "  human name   : Image Gen MCP Server → $HUMAN_NAME"
echo "  CLI command  : image-gen-mcp → $CLI_CMD"
echo

# Text files to update (exclude binary, .git, __pycache__, site, uv.lock)
FILES=$(git ls-files | grep -v -E '\.(png|jpg|gif|ico|woff|woff2|eot|ttf|svg)$' | grep -v 'uv\.lock')

for f in $FILES; do
    if [ -f "$f" ]; then
        sed -i \
            -e "s|image-gen-mcp|$REPO_NAME|g" \
            -e "s|image_gen_mcp|$PYTHON_MODULE|g" \
            -e "s|IMAGE_GEN_MCP|$ENV_PREFIX|g" \
            -e "s|Image Gen MCP Server|$HUMAN_NAME|g" \
            -e "s|image-gen-mcp|$CLI_CMD|g" \
            "$f"
    fi
done

# Rename the source directory
if [ -d "src/image_gen_mcp" ] && [ ! -d "src/$PYTHON_MODULE" ]; then
    mv "src/image_gen_mcp" "src/$PYTHON_MODULE"
    echo "Renamed src/image_gen_mcp → src/$PYTHON_MODULE"
fi

echo
echo "Done. Next steps:"
echo "  1. Review changes: git diff"
echo "  2. Delete this template: rm -rf scripts/"
echo "  3. Update README.md and TEMPLATE.md with your service details"
echo "  4. Add your domain logic in src/$PYTHON_MODULE/_server_tools.py"
echo "  5. Update src/$PYTHON_MODULE/_server_deps.py with your service init"
echo "  6. Run: uv sync && uv run pytest"
