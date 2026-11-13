#!/bin/bash
# Daily System - 前端启动脚本 (Linux/Ubuntu)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/../../frontend"

echo "========================================"
echo "Daily System - 前端启动"
echo "========================================"

cd "$FRONTEND_DIR"

echo ""
echo "检查 Node.js 环境..."
node --version

if [ ! -d "node_modules" ]; then
    echo ""
    echo "安装依赖..."
    npm install
fi

echo ""
echo "启动开发服务器..."
echo "访问地址: http://localhost:5173"
echo ""
npm run dev
