@echo off
chcp 65001 >nul
echo ========================================
echo Daily System - 数据同步
echo ========================================

cd /d "%~dp0..\..\backend"

call venv\Scripts\activate.bat

echo.
echo 同步 Markdown 文件...
python scripts/sync_markdown.py

echo.
echo 同步投资数据...
python scripts/sync_investment.py

echo.
pause
