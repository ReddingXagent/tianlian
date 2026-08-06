.PHONY: help install dev build export-android export-ios export test lint alias-check test-liveness-check check ci-local clean

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

alias-check: ## 路径别名双源漂移守卫 (tsconfig.paths ↔ jest.moduleNameMapper)
	npm run check:alias

test-liveness-check: ## 测试套件活性守卫 (收集数下限33+路径域断言, 拦--passWithNoTests零收集静默放行 F379)
	npm run check:test-liveness

check: build lint alias-check test-liveness-check test ## 完整质量检查 (tsc + eslint + 别名守卫 + 套件活性守卫 + jest)

ci-local: check export ## 本地模拟 CI 流程 (check + export)

clean: ## 清理构建产物
	rm -rf dist node_modules/.cache
