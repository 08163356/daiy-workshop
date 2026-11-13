#!/bin/bash
# Daily System - 后端启动脚本 (Linux/Ubuntu)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../../backend"

echo "========================================"
echo "Daily System - 后端启动"
echo "========================================"

cd "$BACKEND_DIR"

echo ""
echo "检查 Python 环境..."
python3 --version

if [ ! -d "venv" ]; then
    echo ""
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

echo ""
echo "激活虚拟环境..."
source venv/bin/activate

echo ""
echo "安装依赖..."
pip install -r requirements.txt -q

echo ""
echo "启动服务器..."
echo "API 文档: http://localhost:8000/docs"
echo ""
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
