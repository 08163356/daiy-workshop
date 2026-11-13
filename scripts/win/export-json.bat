@echo off
chcp 65001 >nul
echo ========================================
echo Daily System - 导出 JSON 数据
echo ========================================

cd /d "%~dp0..\..\backend"

call venv\Scripts\activate.bat

echo.
echo 导出数据...
python scripts/export_json.py

echo.
pause
