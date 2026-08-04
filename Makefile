.PHONY: help install dev build test lint check auth-keys-check nav-targets-check orphan-pages-check wxml-handlers-check ci-local clean deploy deploy-check

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

auth-keys-check: ## auth存储键双源对账 (app.js↔services/api.js, F240; 委托 npm run check:auth-keys)
	npm run check:auth-keys

nav-targets-check: ## 导航目标↔页面注册双源对账 (跳转url字面量↔app.json pages, F246; 委托 npm run check:nav-targets)
	npm run check:nav-targets

orphan-pages-check: ## 孤儿页面反向可达性对账 (注册页⊆静态导航目标∪tabBar页, F258; 委托 npm run check:orphan-pages)
	npm run check:orphan-pages

wxml-handlers-check: ## WXML事件绑定↔JS方法双源对账 (绑定名↔Page/Component methods, F252; 委托 npm run check:wxml-handlers)
	npm run check:wxml-handlers

check: lint auth-keys-check nav-targets-check orphan-pages-check wxml-handlers-check test ## 完整质量检查 (eslint + auth键对账 + 导航对账 + 孤儿页对账 + 绑定对账 + jest)

ci-local: check ## 本地模拟 CI 流程 (check)

deploy: ## 上传微信小程序 (需配置真appid+密钥)
	node scripts/deploy.js

deploy-check: ## 检查部署就绪状态
	node scripts/deploy.js --check

clean: ## 清理构建产物
	rm -rf coverage node_modules/.cache
