@echo off
chcp 65001 >nul
echo ========================================
echo Daily System - 后端启动
echo ========================================

cd /d "%~dp0..\..\backend"

echo.
echo 检查 Python 环境...
python --version

if not exist "venv" (
    echo.
    echo 创建虚拟环境...
    python -m venv venv
)

echo.
echo 激活虚拟环境...
call venv\Scripts\activate.bat

echo.
echo 安装依赖...
pip install -r requirements.txt -q

echo.
echo 启动服务器...
echo API 文档: http://localhost:8000/docs
echo.
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
