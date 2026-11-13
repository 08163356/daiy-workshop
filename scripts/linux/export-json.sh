#!/bin/bash
# Daily System - 导出 JSON 数据脚本 (Linux/Ubuntu)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../../backend"

echo "========================================"
echo "Daily System - 导出 JSON 数据"
echo "========================================"

cd "$BACKEND_DIR"
source venv/bin/activate

echo ""
echo "导出数据..."
python scripts/export_json.py

echo ""
echo "完成！"
