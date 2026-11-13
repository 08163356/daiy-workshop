#!/bin/bash
# Daily System - 数据同步脚本 (Linux/Ubuntu)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../../backend"

echo "========================================"
echo "Daily System - 数据同步"
echo "========================================"

cd "$BACKEND_DIR"
source venv/bin/activate

echo ""
echo "同步 Markdown 文件..."
python scripts/sync_markdown.py

echo ""
echo "同步投资数据..."
python scripts/sync_investment.py

echo ""
echo "完成！"
