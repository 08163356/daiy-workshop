@echo off
chcp 65001 >nul
echo ========================================
echo Daily System - 完整初始化
echo ========================================

cd /d "%~dp0"

echo.
echo [1/4] 初始化后端...
call init-db.bat

echo.
echo [2/4] 同步数据...
call sync-data.bat

echo.
echo [3/4] 导出 JSON...
call export-json.bat

echo.
echo [4/4] 构建前端...
call build-frontend.bat

echo.
echo ========================================
echo 初始化完成！
echo ========================================
pause
