# Makefile for AirLLM-EasyTUI

.PHONY: help install install-dev clean run test lint format check

help: ## 显示帮助信息
	@echo "AirLLM-EasyTUI - 可用命令:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## 安装生产依赖
	pip install -r requirements.txt

install-dev: ## 安装开发依赖（生产依赖 + 开发工具）
	pip install -r requirements.txt
	pip install pytest pytest-cov black ruff mypy

clean: ## 清理构建文件和缓存
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	rm -rf .eggs/ build/ dist/ *.egg-info/
	rm -rf venv/ .venv/

run: ## 运行应用程序
	python airllm_easy_tui.py

test: ## 运行测试
	pytest tests/ -v --cov=. --cov-report=html

lint: ## 代码检查
	ruff check .
	ruff format --check .

format: ## 代码格式化
	ruff format .
	ruff check --fix .

check: ## 运行所有检查
	$(MAKE) lint
	$(MAKE) test

debug: ## 调试模式运行（设置环境变量）
	DEBUG=1 python airllm_easy_tui.py
