.PHONY: help install dev build test lint check auth-keys-check dead-handlers-check event-usage-check native-attrs-check json-keys-check nav-targets-check orphan-components-check orphan-pages-check permission-apis-check prop-usage-check request-source-check setdata-payload-check setdata-perf-check storage-keys-check wxml-handlers-check wxs-isolation-check ci-local clean deploy deploy-check

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

dead-handlers-check: ## 死handler反向可达性对账 (js方法⊆wxml绑定∪this调用, F264; 委托 npm run check:dead-handlers)
	npm run check:dead-handlers

event-usage-check: ## 组件事件对账 (冒号式绑定名⊆triggerEvent触发名集合∧无冒号式⊆触发名∪原生事件, 失配=绑定永不触发的静默no-op, F329; 委托 npm run check:event-usage)
	npm run check:event-usage

native-attrs-check: ## 原生组件属性域对账 (image/button/input属性名⊆官方域∪豁免域∧枚举静态值⊆官方值域, 拼错=微信静默忽略/回落默认值零报错, F337→F344泛化; 委托 npm run check:native-attrs)
	npm run check:native-attrs

json-keys-check: ## JSON配置键白名单对账 (app/页面/组件json键⊆官方键域+枚举值域+tabBar/preloadRule↔pages跨源, F311; 委托 npm run check:json-keys)
	npm run check:json-keys

nav-targets-check: ## 导航目标↔页面注册双源对账 (跳转url字面量↔app.json pages, F246; 委托 npm run check:nav-targets)
	npm run check:nav-targets

orphan-components-check: ## 孤儿组件反向对账 (组件实体⊆usingComponents引用集, F284; 委托 npm run check:orphan-components)
	npm run check:orphan-components
orphan-pages-check: ## 孤儿页面反向可达性对账 (注册页⊆静态导航目标∪tabBar页, F258; 委托 npm run check:orphan-pages)
	npm run check:orphan-pages
permission-apis-check: ## 隐私API↔app.json声明双向对账 (调用映射⊆requiredPrivateInfos⊆调用映射+scope desc, F277; 委托 npm run check:permission-apis)
	npm run check:permission-apis

prop-usage-check: ## 组件properties↔wxml使用属性对账 (组件标签⊆usingComponents注册∧使用属性⊆properties声明∪通用域, F323; 委托 npm run check:prop-usage)
	npm run check:prop-usage

request-source-check: ## 请求出口↔URL声明单一源对账 (wx.request调用点⊆api.js + http(s)字面量⊆config/index.js, F292; 委托 npm run check:request-source)
	npm run check:request-source

setdata-payload-check: ## setData负载体积守卫 (内联字面量键≤8·长度≤512, F317; 委托 npm run check:setdata-payload)
	npm run check:setdata-payload

setdata-perf-check: ## setData性能反模式对账 (循环体内setData∩调用点=∅ + 相邻同步setData对=∅, F298; 委托 npm run check:setdata-perf)
	npm run check:setdata-perf

storage-keys-check: ## storage键生命周期双向对账 (get键⊆set键⊆get键全仓, F270; 委托 npm run check:storage-keys)
	npm run check:storage-keys

wxml-handlers-check: ## WXML事件绑定↔JS方法双源对账 (绑定名↔Page/Component methods, F252; 委托 npm run check:wxml-handlers)
	npm run check:wxml-handlers

wxs-isolation-check: ## wxs视图层隔离双向对账 (wxs实体↔<wxs src>声明双向+js禁引用, F305; 委托 npm run check:wxs-isolation)
	npm run check:wxs-isolation

check: lint auth-keys-check dead-handlers-check event-usage-check native-attrs-check json-keys-check nav-targets-check orphan-components-check orphan-pages-check permission-apis-check prop-usage-check request-source-check setdata-payload-check setdata-perf-check storage-keys-check wxml-handlers-check wxs-isolation-check test ## 完整质量检查 (eslint + auth键对账 + 死handler对账 + 组件事件对账 + 原生组件属性对账 + JSON配置键对账 + 导航对账 + 孤儿组件对账 + 孤儿页对账 + 隐私API对账 + 组件属性对账 + 请求单一源对账 + setData负载守卫 + setData性能对账 + storage键对账 + 绑定对账 + wxs隔离对账 + jest)

ci-local: check ## 本地模拟 CI 流程 (check)

deploy: ## 上传微信小程序 (需配置真appid+密钥)
	node scripts/deploy.js

deploy-check: ## 检查部署就绪状态
	node scripts/deploy.js --check

clean: ## 清理构建产物
	rm -rf coverage node_modules/.cache
