@echo off
REM AirLLM-EasyTUI 开发脚本 (Windows)

setlocal enabledelayedexpansion

REM 颜色定义
set "RED=[91m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "NC=[0m"

REM 打印函数
:print_info
echo %BLUE%[INFO]%NC% %~1
goto :eof

:print_success
echo %GREEN%[SUCCESS]%NC% %~1
goto :eof

:print_warning
echo %YELLOW%[WARNING]%NC% %~1
goto :eof

:print_error
echo %RED%[ERROR]%NC% %~1
goto :eof

REM 检查 Python 版本
:check_python_version
call :print_info "检查 Python 版本..."
python --version 2>nul
if errorlevel 1 (
    call :print_error "未找到 Python，请先安装 Python 3.11+"
    exit /b 1
)
goto :eof

REM 创建虚拟环境
:setup_venv
call :print_info "设置虚拟环境..."
if exist "venv" (
    call :print_warning "虚拟环境已存在，跳过创建"
) else (
    python -m venv venv
    call :print_success "虚拟环境创建完成"
)
goto :eof

REM 安装依赖
:install_deps
call :print_info "安装依赖..."
if exist "requirements.txt" (
    call venv\Scripts\pip install -r requirements.txt
    call :print_success "依赖安装完成"
) else (
    call :print_error "requirements.txt 不存在"
    exit /b 1
)
goto :eof

REM 安装开发工具
:install_dev_tools
call :print_info "安装开发工具..."
call venv\Scripts\pip install pytest pytest-cov black ruff mypy
call :print_success "开发工具安装完成"
goto :eof

REM 运行测试
:run_tests
call :print_info "运行测试..."
call venv\Scripts\pytest tests/ -v --cov=. --cov-report=html --cov-report=term
goto :eof

REM 代码检查
:run_lint
call :print_info "运行代码检查..."

REM Ruff
where ruff >nul 2>&1
if not errorlevel 1 (
    call :print_info "运行 Ruff..."
    ruff check .
) else (
    call :print_warning "Ruff 未安装，跳过代码检查"
)

REM Black
where black >nul 2>&1
if not errorlevel 1 (
    call :print_info "运行 Black..."
    black --check .
) else (
    call :print_warning "Black 未安装，跳过代码格式检查"
)
goto :eof

REM 格式化代码
:format_code
call :print_info "格式化代码..."

where ruff >nul 2>&1
if not errorlevel 1 (
    ruff format .
)

where black >nul 2>&1
if not errorlevel 1 (
    black .
)

call :print_success "代码格式化完成"
goto :eof

REM 运行应用程序
:run_app
call :print_info "运行应用程序..."
call venv\Scripts\python airllm_easy_tui.py %*
goto :eof

REM 创建配置文件
:setup_config
call :print_info "创建配置文件..."

if not exist "config.yaml" (
    if exist "config.example.yaml" (
        copy config.example.yaml config.yaml
        call :print_success "配置文件已创建（config.yaml）"
        call :print_warning "请根据需要修改 config.yaml"
    ) else (
        call :print_error "config.example.yaml 不存在"
        exit /b 1
    )
) else (
    call :print_info "配置文件已存在"
)
goto :eof

REM 主菜单
:show_menu
echo.
echo =========================================
echo   AirLLM-EasyTUI 开发工具 (Windows)
echo =========================================
echo 1. 完整设置（安装依赖 + 开发工具）
echo 2. 仅安装依赖
echo 3. 仅安装开发工具
echo 4. 运行测试
echo 5. 代码检查
echo 6. 代码格式化
echo 7. 运行应用程序
echo 8. 创建配置文件
echo 9. 显示菜单
echo 0. 退出
echo =========================================
set /p choice="请选择操作 [0-9]: "

if "%choice%"=="1" (
    call :check_python_version
    call :setup_venv
    call :install_deps
    call :install_dev_tools
    call :print_success "设置完成！"
    goto :show_menu
)

if "%choice%"=="2" (
    call :install_deps
    goto :show_menu
)

if "%choice%"=="3" (
    call :install_dev_tools
    goto :show_menu
)

if "%choice%"=="4" (
    call :run_tests
    goto :show_menu
)

if "%choice%"=="5" (
    call :run_lint
    goto :show_menu
)

if "%choice%"=="6" (
    call :format_code
    goto :show_menu
)

if "%choice%"=="7" (
    call :run_app
    goto :show_menu
)

if "%choice%"=="8" (
    call :setup_config
    goto :show_menu
)

if "%choice%"=="9" (
    goto :show_menu
)

if "%choice%"=="0" (
    call :print_info "退出..."
    exit /b 0
)

call :print_error "无效选择: %choice%"
goto :show_menu

REM 主函数
:main
REM 激活虚拟环境
if exist "venv" (
    call venv\Scripts\activate.bat
)

REM 如果提供了参数，直接执行
if not "%~1"=="" (
    if "%~1"=="setup" (
        call :check_python_version
        call :setup_venv
        call :install_deps
        call :install_dev_tools
        call :print_success "设置完成！"
        exit /b 0
    )

    if "%~1"=="test" (
        call :run_tests
        exit /b 0
    )

    if "%~1"=="lint" (
        call :run_lint
        exit /b 0
    )

    if "%~1"=="format" (
        call :format_code
        exit /b 0
    )

    if "%~1"=="run" (
        shift
        call :run_app %*
        exit /b 0
    )

    if "%~1"=="config" (
        call :setup_config
        exit /b 0
    )

    call :print_error "未知命令: %~1"
    exit /b 1
)

REM 交互模式
:show_menu

endlocal
