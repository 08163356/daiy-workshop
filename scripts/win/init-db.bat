@echo off
chcp 65001 >nul
echo ========================================
echo Daily System - 数据库初始化
echo ========================================

cd /d "%~dp0..\..\backend"

if not exist "venv" (
    echo 创建虚拟环境...
    python -m venv venv
)

call venv\Scripts\activate.bat
pip install -r requirements.txt -q

echo.
echo 初始化数据库...
python scripts/init_db.py

echo.
pause
