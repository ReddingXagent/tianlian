.PHONY: help install dev build test lint check ci-local clean deploy deploy-check

help: ## 显示所有命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## 安装依赖
	npm install

dev: ## 启动微信开发者工具调试 (需微信开发者工具)
	@echo "⚠ 微信小程序无独立dev server, 用微信开发者工具打开本目录"

build: ## 结构检查 (微信小程序无需tsc)
	node scripts/check-mp-structure.js

test: ## 运行测试
	npm test -- --coverage

lint: ## ESLint 检查 (委托 npm run lint, 单一源)
	npm run lint

check: lint test ## 完整质量检查 (eslint + jest)

ci-local: check ## 本地模拟 CI 流程 (check)

deploy: ## 上传微信小程序 (需配置真appid+密钥)
	node scripts/deploy.js

deploy-check: ## 检查部署就绪状态
	node scripts/deploy.js --check

clean: ## 清理构建产物
	rm -rf coverage node_modules/.cache
