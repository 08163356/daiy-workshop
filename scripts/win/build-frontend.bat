@echo off
chcp 65001 >nul
echo ========================================
echo Daily System - 前端构建
echo ========================================

cd /d "%~dp0..\..\frontend"

echo.
echo 安装依赖...
npm install

echo.
echo 构建生产版本...
npm run build

echo.
echo 构建完成！产物在 frontend/dist 目录
echo.
pause
