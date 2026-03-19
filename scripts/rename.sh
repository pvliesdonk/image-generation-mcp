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
#   image-generation-mcp  → <repo-name>
#   image_generation_mcp  → <python_module>
#   IMAGE_GENERATION_MCP               → <ENV_PREFIX>
#   Image Generation MCP Server  → <Human Name>
#   (CLI command uses the same repo-name value)
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
echo "Renaming template:"
echo "  repo name    : image-generation-mcp → $REPO_NAME"
echo "  python module: image_generation_mcp → $PYTHON_MODULE"
echo "  env prefix   : IMAGE_GENERATION_MCP → $ENV_PREFIX"
echo "  human name   : Image Generation MCP Server → $HUMAN_NAME"
echo

# Text files to update (exclude binary, .git, __pycache__, site, uv.lock)
FILES=$(git ls-files | grep -v -E '\.(png|jpg|gif|ico|woff|woff2|eot|ttf|svg)$' | grep -v 'uv\.lock')

for f in $FILES; do
    if [ -f "$f" ]; then
        sed -i \
            -e "s|image-generation-mcp|$REPO_NAME|g" \
            -e "s|image_generation_mcp|$PYTHON_MODULE|g" \
            -e "s|IMAGE_GENERATION_MCP|$ENV_PREFIX|g" \
            -e "s|Image Generation MCP Server|$HUMAN_NAME|g" \
            "$f"
    fi
done

# Rename the source directory
if [ -d "src/image_generation_mcp" ] && [ ! -d "src/$PYTHON_MODULE" ]; then
    mv "src/image_generation_mcp" "src/$PYTHON_MODULE"
    echo "Renamed src/image_generation_mcp → src/$PYTHON_MODULE"
fi

echo
echo "Done. Next steps:"
echo "  1. Review changes: git diff"
echo "  2. Delete this template: rm -rf scripts/"
echo "  3. Update README.md and TEMPLATE.md with your service details"
echo "  4. Add your domain logic in src/$PYTHON_MODULE/_server_tools.py"
echo "  5. Update src/$PYTHON_MODULE/_server_deps.py with your service init"
echo "  6. Run: uv sync && uv run pytest"
