#!/bin/bash
# AirLLM-EasyTUI 开发脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印函数
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查 Python 版本
check_python_version() {
    print_info "检查 Python 版本..."
    python_version=$(python --version 2>&1 | awk '{print $2}')
    python_major=$(echo $python_version | cut -d. -f1)
    python_minor=$(echo $python_version | cut -d. -f2)

    if [ "$python_major" -lt 3 ] || ([ "$python_major" -eq 3 ] && [ "$python_minor" -lt 11 ]); then
        print_error "Python 3.11 或更高版本是必需的（当前: $python_version）"
        exit 1
    fi

    print_success "Python 版本: $python_version"
}

# 创建虚拟环境
setup_venv() {
    print_info "设置虚拟环境..."

    if [ -d "venv" ]; then
        print_warning "虚拟环境已存在，跳过创建"
    else
        python -m venv venv
        print_success "虚拟环境创建完成"
    fi

    # 激活虚拟环境
    print_info "激活虚拟环境..."
    source venv/bin/activate
}

# 安装依赖
install_deps() {
    print_info "安装依赖..."

    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
        print_success "依赖安装完成"
    else
        print_error "requirements.txt 不存在"
        exit 1
    fi
}

# 安装开发工具
install_dev_tools() {
    print_info "安装开发工具..."

    pip install pytest pytest-cov black ruff mypy
    print_success "开发工具安装完成"
}

# 运行测试
run_tests() {
    print_info "运行测试..."
    pytest tests/ -v --cov=. --cov-report=html --cov-report=term
}

# 代码检查
run_lint() {
    print_info "运行代码检查..."

    # Ruff
    if command -v ruff &> /dev/null; then
        print_info "运行 Ruff..."
        ruff check .
    else
        print_warning "Ruff 未安装，跳过代码检查"
    fi

    # Black
    if command -v black &> /dev/null; then
        print_info "运行 Black..."
        black --check .
    else
        print_warning "Black 未安装，跳过代码格式检查"
    fi
}

# 格式化代码
format_code() {
    print_info "格式化代码..."

    if command -v ruff &> /dev/null; then
        ruff format .
    fi

    if command -v black &> /dev/null; then
        black .
    fi

    print_success "代码格式化完成"
}

# 运行应用程序
run_app() {
    print_info "运行应用程序..."
    python airllm_easy_tui.py "$@"
}

# 创建配置文件
setup_config() {
    print_info "创建配置文件..."

    if [ ! -f "config.yaml" ] && [ -f "config.example.yaml" ]; then
        cp config.example.yaml config.yaml
        print_success "配置文件已创建（config.yaml）"
        print_warning "请根据需要修改 config.yaml"
    else
        print_info "配置文件已存在"
    fi
}

# 主菜单
show_menu() {
    echo ""
    echo "========================================="
    echo "  AirLLM-EasyTUI 开发工具"
    echo "========================================="
    echo "1. 完整设置（安装依赖 + 开发工具）"
    echo "2. 仅安装依赖"
    echo "3. 仅安装开发工具"
    echo "4. 运行测试"
    echo "5. 代码检查"
    echo "6. 代码格式化"
    echo "7. 运行应用程序"
    echo "8. 创建配置文件"
    echo "9. 显示菜单"
    echo "0. 退出"
    echo "========================================="
    echo -n "请选择操作 [0-9]: "
}

# 主函数
main() {
    # 激活虚拟环境
    if [ -d "venv" ]; then
        source venv/bin/activate
    fi

    # 如果提供了参数，直接执行
    if [ $# -gt 0 ]; then
        case $1 in
            setup)
                check_python_version
                setup_venv
                install_deps
                install_dev_tools
                print_success "设置完成！"
                ;;
            test)
                run_tests
                ;;
            lint)
                run_lint
                ;;
            format)
                format_code
                ;;
            run)
                shift
                run_app "$@"
                ;;
            config)
                setup_config
                ;;
            *)
                show_menu
                ;;
        esac
        return 0
    fi

    # 交互模式
    while true; do
        show_menu
        read -r choice

        case $choice in
            1)
                check_python_version
                setup_venv
                install_deps
                install_dev_tools
                print_success "设置完成！"
                ;;
            2)
                install_deps
                ;;
            3)
                install_dev_tools
                ;;
            4)
                run_tests
                ;;
            5)
                run_lint
                ;;
            6)
                format_code
                ;;
            7)
                shift
                run_app "$@"
                ;;
            8)
                setup_config
                ;;
            9)
                # 重新显示菜单
                continue
                ;;
            0)
                print_info "退出..."
                exit 0
                ;;
            *)
                print_error "无效选择: $choice"
                ;;
        esac
    done
}

# 运行主函数
main "$@"
