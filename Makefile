.PHONY: help install dev build export-android export-ios export test lint check ci-local clean

help: ## 显示所有命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## 安装依赖
	npm install

dev: ## 启动 Expo Dev Server
	npm start

build: ## TypeScript 类型检查
	npx tsc --noEmit

export-android: ## 导出 Android bundle
	npx expo export --platform android

export-ios: ## 导出 iOS bundle
	npx expo export --platform ios

export: build export-android export-ios ## 导出全平台 bundle

test: ## 运行测试
	npm test -- --coverage

lint: ## ESLint 检查
	npx eslint . --max-warnings 0

check: build lint test ## 完整质量检查 (tsc + eslint + jest)

ci-local: check export ## 本地模拟 CI 流程 (check + export)

clean: ## 清理构建产物
	rm -rf dist node_modules/.cache
