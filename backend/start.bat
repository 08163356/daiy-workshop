@echo off
chcp 65001 >nul
echo ========================================
echo 读书管理系统 - 后端启动
echo ========================================

echo.
echo 检查 Python 环境...
python --version

echo.
echo 安装依赖...
pip install -r requirements.txt -q

echo.
echo 初始化数据库...
python scripts/init_db.py

echo.
echo 同步 Markdown 文件...
python scripts/sync_markdown.py

echo.
echo 启动服务器...
echo API 文档: http://localhost:8000/docs
echo.
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
