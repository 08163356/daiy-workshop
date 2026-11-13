# 读书管理系统 - 后端启动脚本 (PowerShell)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "读书管理系统 - 后端启动" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 检查 Python
Write-Host "`n检查 Python 环境..." -ForegroundColor Yellow
python --version

# 创建虚拟环境（如果不存在）
if (-not (Test-Path "venv")) {
    Write-Host "`n创建虚拟环境..." -ForegroundColor Yellow
    python -m venv venv
}

# 激活虚拟环境
Write-Host "`n激活虚拟环境..." -ForegroundColor Yellow
.\venv\Scripts\Activate.ps1

# 安装依赖
Write-Host "`n安装依赖..." -ForegroundColor Yellow
pip install -r requirements.txt -q

# 初始化数据库
Write-Host "`n初始化数据库..." -ForegroundColor Yellow
python scripts/init_db.py

# 同步 Markdown
Write-Host "`n同步 Markdown 文件..." -ForegroundColor Yellow
python scripts/sync_markdown.py

# 启动服务器
Write-Host "`n启动服务器..." -ForegroundColor Green
Write-Host "API 文档: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
