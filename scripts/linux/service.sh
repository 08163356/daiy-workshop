#!/bin/bash
# Daily System - 服务管理脚本 (Ubuntu systemd)
# 用法: ./service.sh [install|start|stop|restart|status|logs|uninstall]

set -e

# 配置 - 服务器上的路径
PROJECT_NAME="daily-system"
PROJECT_DIR="/var/www/${PROJECT_NAME}"
BACKEND_SERVICE="${PROJECT_NAME}-backend"
USER="www-data"
GROUP="www-data"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}Daily System - 服务管理${NC}"
    echo -e "${CYAN}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}➡️  $1${NC}"
}

# 安装 systemd 服务
install_service() {
    print_header
    print_info "安装 systemd 服务..."
    
    # 检查项目目录
    if [ ! -d "$PROJECT_DIR" ]; then
        print_error "项目目录不存在: $PROJECT_DIR"
        exit 1
    fi
    
    # 创建后端服务文件
    sudo tee /etc/systemd/system/${BACKEND_SERVICE}.service > /dev/null << EOF
[Unit]
Description=Daily System Backend (FastAPI)
After=network.target

[Service]
Type=simple
User=${USER}
Group=${GROUP}
WorkingDirectory=${PROJECT_DIR}/backend
Environment="PATH=${PROJECT_DIR}/backend/venv/bin"
ExecStart=${PROJECT_DIR}/backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

# 日志
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${BACKEND_SERVICE}

[Install]
WantedBy=multi-user.target
EOF

    print_success "服务文件已创建: /etc/systemd/system/${BACKEND_SERVICE}.service"
    
    # 重载 systemd
    sudo systemctl daemon-reload
    
    # 启用开机启动
    sudo systemctl enable ${BACKEND_SERVICE}
    
    print_success "服务已安装并设置开机启动"
}

# 启动服务
start_service() {
    print_header
    print_info "启动服务..."
    
    sudo systemctl start ${BACKEND_SERVICE}
    
    sleep 2
    
    if systemctl is-active --quiet ${BACKEND_SERVICE}; then
        print_success "后端服务已启动"
    else
        print_error "后端服务启动失败"
        sudo journalctl -u ${BACKEND_SERVICE} -n 20 --no-pager
    fi
}

# 停止服务
stop_service() {
    print_header
    print_info "停止服务..."
    
    sudo systemctl stop ${BACKEND_SERVICE}
    
    print_success "服务已停止"
}

# 重启服务
restart_service() {
    print_header
    print_info "重启服务..."
    
    sudo systemctl restart ${BACKEND_SERVICE}
    
    sleep 2
    
    if systemctl is-active --quiet ${BACKEND_SERVICE}; then
        print_success "服务重启成功"
    else
        print_error "服务重启失败"
    fi
}

# 查看状态
show_status() {
    print_header
    print_info "服务状态:"
    echo ""
    
    echo -e "${CYAN}=== 后端服务 ===${NC}"
    sudo systemctl status ${BACKEND_SERVICE} --no-pager || true
    
    echo ""
    echo -e "${CYAN}=== 端口监听 ===${NC}"
    sudo ss -tlnp | grep -E ":(8000|5173)" || echo "无监听端口"
    
    echo ""
    echo -e "${CYAN}=== 进程信息 ===${NC}"
    ps aux | grep -E "(uvicorn|node)" | grep -v grep || echo "无相关进程"
}

# 查看日志
show_logs() {
    print_header
    print_info "最近日志 (最后100行):"
    echo ""
    
    sudo journalctl -u ${BACKEND_SERVICE} -n 100 --no-pager
}

# 实时日志
follow_logs() {
    print_header
    print_info "实时日志 (Ctrl+C 退出):"
    echo ""
    
    sudo journalctl -u ${BACKEND_SERVICE} -f
}

# 卸载服务
uninstall_service() {
    print_header
    print_info "卸载服务..."
    
    # 停止服务
    sudo systemctl stop ${BACKEND_SERVICE} 2>/dev/null || true
    
    # 禁用开机启动
    sudo systemctl disable ${BACKEND_SERVICE} 2>/dev/null || true
    
    # 删除服务文件
    sudo rm -f /etc/systemd/system/${BACKEND_SERVICE}.service
    
    # 重载 systemd
    sudo systemctl daemon-reload
    
    print_success "服务已卸载"
}

# 显示帮助
show_help() {
    print_header
    echo ""
    echo "用法: $0 [命令]"
    echo ""
    echo "命令:"
    echo "  install   - 安装 systemd 服务"
    echo "  start     - 启动服务"
    echo "  stop      - 停止服务"
    echo "  restart   - 重启服务"
    echo "  status    - 查看服务状态"
    echo "  logs      - 查看最近日志"
    echo "  follow    - 实时查看日志"
    echo "  uninstall - 卸载服务"
    echo "  help      - 显示帮助"
    echo ""
}

# 主逻辑
case "${1:-help}" in
    install)
        install_service
        ;;
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    follow)
        follow_logs
        ;;
    uninstall)
        uninstall_service
        ;;
    help|*)
        show_help
        ;;
esac
