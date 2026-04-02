#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "Running Telegram proxy patch..."
echo ""

python3 "$SCRIPT_DIR/patch_proxy_tg.py"
