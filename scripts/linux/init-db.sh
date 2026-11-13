#!/bin/bash
# Daily System - 数据库初始化脚本 (Linux/Ubuntu)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../../backend"

echo "========================================"
echo "Daily System - 数据库初始化"
echo "========================================"

cd "$BACKEND_DIR"

if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt -q

echo ""
echo "初始化数据库..."
python scripts/init_db.py

echo ""
echo "完成！"
