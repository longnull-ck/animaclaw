# ============================================================
# Anima — 快捷命令
# ============================================================

.PHONY: help build up down logs restart init shell clean

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## 构建 Docker 镜像
	docker compose build

up: ## 启动 Anima（后台运行）
	docker compose up -d

down: ## 停止 Anima
	docker compose down

logs: ## 查看实时日志
	docker compose logs -f anima

restart: ## 重启 Anima
	docker compose restart anima

init: ## 初始化 Anima 员工身份（交互式）
	docker compose run --rm anima python run.py init

shell: ## 进入容器 Shell
	docker compose exec anima bash

status: ## 查看状态
	docker compose exec anima python run.py status

clean: ## 清理镜像和数据卷（⚠️ 会删除所有数据）
	docker compose down -v --rmi local
