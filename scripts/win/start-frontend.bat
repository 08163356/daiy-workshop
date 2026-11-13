@echo off
chcp 65001 >nul
echo ========================================
echo Daily System - 前端启动
echo ========================================

cd /d "%~dp0..\..\frontend"

echo.
echo 检查 Node.js 环境...
node --version

if not exist "node_modules" (
    echo.
    echo 安装依赖...
    npm install
)

echo.
echo 启动开发服务器...
echo 访问地址: http://localhost:5173
echo.
npm run dev
