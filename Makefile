# 天链运维 App - Makefile
# 本地构建与验证快捷命令

.PHONY: help install dev build test lint doctor version-check alias-check node-check check clean export-android export-ios bundle-size ci-local

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## 安装依赖
	npm ci

dev: ## 启动开发服务器
	npx expo start

build: ## TypeScript 编译检查 (委托 npm run typecheck, 调用点单一源 F206)
	npm run typecheck

export-android: ## 导出 Android JS Bundle (委托 npm run build:android, 调用点单一源 F212/F206)
	npm run build:android -- --output-dir /tmp/ops-export-android

export-ios: ## 导出 iOS JS Bundle (委托 npm run build:ios, 调用点单一源 F212/F206)
	npm run build:ios -- --output-dir /tmp/ops-export-ios

bundle-size: ## JS Bundle 体积门控 (需先 export-android/export-ios)
	./scripts/bundle-size.sh

doctor: ## Expo 项目体检 (依赖版本/配置一致性, 与CI一致)
	npm run doctor

test: ## 运行单元测试 (委托 npm test, 调用点单一源 F206)
	npm test -- --coverage

lint: ## ESLint 检查 (与 npm run lint/CI 一致, 全仓含配置文件)
	npm run lint

version-check: ## 版本双源漂移守卫 (package.json vs app.json, 委托 npm run check:version, F224)
	npm run check:version

alias-check: ## 路径别名双源漂移守卫 (tsconfig.paths vs jest.moduleNameMapper, 委托 npm run check:alias, F231)
	npm run check:alias

node-check: ## node版本双源漂移守卫 (engines.node vs CI node-version, 委托 npm run check:node, F237)
	npm run check:node

check: version-check alias-check node-check build lint test ## 全量检查 (版本同步 + 别名同步 + node基线同步 + tsc + eslint + jest)

ci-local: check doctor export-android export-ios bundle-size ## 模拟 CI 全流程 (检查 + doctor体检 + 双平台导出 + 体积门控)

clean: ## 清理构建产物
	rm -rf /tmp/ops-export-android /tmp/ops-export-ios coverage dist
	rm -f *.tsbuildinfo
