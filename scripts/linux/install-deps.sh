#!/bin/bash
# Daily System - 环境安装脚本 (仅安装依赖，不部署)

set -e

echo "========================================"
echo "Daily System - 环境安装"
echo "========================================"

echo ""
echo "更新系统..."
sudo apt update

echo ""
echo "安装基础工具..."
sudo apt install -y curl wget git

# Node.js
echo ""
echo "安装 Node.js 20.x..."
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
fi
echo "Node.js: $(node --version)"
echo "npm: $(npm --version)"

# Python
echo ""
echo "安装 Python..."
sudo apt install -y python3 python3-pip python3-venv
echo "Python: $(python3 --version)"

# Nginx
echo ""
echo "安装 Nginx..."
sudo apt install -y nginx
sudo systemctl enable nginx
sudo systemctl start nginx
echo "Nginx: $(nginx -v 2>&1)"

echo ""
echo "========================================"
echo "环境安装完成！"
echo "========================================"
