#!/bin/bash
# Daily System - 完整初始化脚本 (Linux/Ubuntu)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo "Daily System - 完整初始化"
echo "========================================"

cd "$SCRIPT_DIR"

echo ""
echo "[1/4] 初始化后端..."
bash init-db.sh

echo ""
echo "[2/4] 同步数据..."
bash sync-data.sh

echo ""
echo "[3/4] 导出 JSON..."
bash export-json.sh

echo ""
echo "[4/4] 构建前端..."
bash build-frontend.sh

echo ""
echo "========================================"
echo "初始化完成！"
echo "========================================"
