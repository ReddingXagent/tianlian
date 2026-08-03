# 天链运维 App - Makefile
# 本地构建与验证快捷命令

.PHONY: help install dev build test lint check clean export-android export-ios ci-local

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## 安装依赖
	npm ci

dev: ## 启动开发服务器
	npx expo start

build: ## TypeScript 编译检查
	npx tsc --noEmit

export-android: ## 导出 Android JS Bundle
	npx expo export --platform android --output-dir /tmp/ops-export-android

export-ios: ## 导出 iOS JS Bundle
	npx expo export --platform ios --output-dir /tmp/ops-export-ios

test: ## 运行单元测试
	npx jest --coverage

lint: ## ESLint 检查
	npx eslint src/ --ext .ts,.tsx

check: build lint test ## 全量检查 (tsc + eslint + jest)

ci-local: check export-android ## 模拟 CI 全流程 (检查 + Android 导出)

clean: ## 清理构建产物
	rm -rf /tmp/ops-export-android /tmp/ops-export-ios coverage
	rm -f *.tsbuildinfo
