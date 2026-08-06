# 天链运维 App - Makefile
# 本地构建与验证快捷命令

.PHONY: help install dev build test lint doctor version-check alias-check node-check guard-wiring-check env-defaults-check unused-deps-check ci-parity-check engine-strict-check app-version-source-check expo-plugins-check updates-channel-check brand-color-check build-number-parity-check easignore-secrets-check unused-assets-check asset-size-check eas-env-check check clean export-android export-ios bundle-size ci-local

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

guard-wiring-check: ## 守卫接线三源一致性守卫 (package.json check:* vs Makefile check链 vs CI, 委托 npm run check:guard-wiring, F250)
	npm run check:guard-wiring


env-defaults-check: ## 环境变量双源漂移守卫 (代码读取键↔.env.example模板键+fallback值对账, 委托 npm run check:env-defaults, F256)
	npm run check:env-defaults

unused-deps-check: ## 未使用依赖守卫 (生产依赖import/plugins/隐式白名单三形态, 委托 npm run check:unused-deps, F262)
	npm run check:unused-deps

ci-parity-check: ## CI门控链↔ci-local双源漂移守卫 (ci.yml run步骤 vs ci-local递归展开, 委托 npm run check:ci-parity)
	npm run check:ci-parity

engine-strict-check: ## engines.node执行力双源漂移守卫 (.npmrc engine-strict ↔ engines.node成对, 委托 npm run check:engine-strict)
	npm run check:engine-strict

app-version-source-check: ## appVersionSource双源成对守卫 (eas.json appVersionSource=local ↔ app.json versionCode/buildNumber, 委托 npm run check:app-version-source, F288)
	npm run check:app-version-source

expo-plugins-check: ## expo.plugins↔package.json依赖双源成对守卫 (声明侧↔供给侧, 委托 npm run check:expo-plugins, F296)
	npm run check:expo-plugins
updates-channel-check: ## OTA更新通道双源成对守卫 (app.json updates.url ↔ eas.json projectId, 委托 npm run check:updates-channel, F302)
	npm run check:updates-channel

brand-color-check: ## 品牌色双源漂移守卫 (app.json splash.backgroundColor ↔ adaptiveIcon.backgroundColor, 委托 npm run check:brand-color, F309)
	npm run check:brand-color

build-number-parity-check: ## versionCode↔buildNumber数值配对守卫 (app.json android.versionCode ↔ ios.buildNumber, 委托 npm run check:build-number-parity, F315)
	npm run check:build-number-parity

easignore-secrets-check: ## .gitignore↔.easignore敏感排除超集守卫 (凭据类模式双侧对账, 委托 npm run check:easignore-secrets, F321)
	npm run check:easignore-secrets

unused-assets-check: ## assets磁盘↔引用源反向对账守卫 (死资产检测, 委托 npm run check:unused-assets, F327)
	npm run check:unused-assets

asset-size-check: ## assets体积上限守卫 (单文件≤512KB/总≤2048KB, 委托 npm run check:asset-size, F334)
	npm run check:asset-size

eas-env-check: ## eas.json构建期env↔.env.example模板对账守卫 (EXPO_PUBLIC_*键登记+值级对账, 委托 npm run check:eas-env, F342)
	npm run check:eas-env
app-identity-check: ## 跨平台身份一致性守卫 (android.package↔ios.bundleIdentifier, 委托 npm run check:app-identity, F354)
	npm run check:app-identity

check: version-check alias-check node-check guard-wiring-check env-defaults-check unused-deps-check ci-parity-check engine-strict-check app-version-source-check expo-plugins-check updates-channel-check brand-color-check build-number-parity-check easignore-secrets-check unused-assets-check asset-size-check eas-env-check app-identity-check build lint test ## 全量检查 (版本同步 + 别名同步 + node基线同步 + 守卫接线同步 + 死依赖 + CI同构 + 版本号成对 + 插件依赖成对 + OTA通道成对 + 品牌色一致 + 构建序号配对 + 敏感排除超集 + 死资产对账 + 体积上限 + EAS env对账 + 跨平台身份一致 + tsc + eslint + jest)

ci-local: check doctor export-android export-ios bundle-size ## 模拟 CI 全流程 (检查 + doctor体检 + 双平台导出 + 体积门控)

clean: ## 清理构建产物
	rm -rf /tmp/ops-export-android /tmp/ops-export-ios coverage dist
	rm -f *.tsbuildinfo
