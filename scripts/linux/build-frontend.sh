#!/bin/bash
# Daily System - 前端构建脚本 (Linux/Ubuntu)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/../../frontend"

echo "========================================"
echo "Daily System - 前端构建"
echo "========================================"

cd "$FRONTEND_DIR"

echo ""
echo "安装依赖..."
npm install

echo ""
echo "构建生产版本..."
npm run build

echo ""
echo "构建完成！产物在 frontend/dist 目录"
