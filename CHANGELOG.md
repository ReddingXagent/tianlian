# Changelog — tianlian-user-mp

格式参考 Keep a Changelog。本仓为微信小程序用户端。

## [Unreleased]

### Added
- 孤儿页面反向可达性双源对账守卫（F258）：F246 只挡正向“跳转目标⊆注册页”（跳到未注册页），反方向“注册了但无任何入口的死页面”零断言——新注册页面未写导航入口=用户永远无法到达（功能静默不可用）/删除或改名全部跳转调用点但保留注册=孤儿页（死代码+包体膨胀）/tabBar 移除某页但 pages 保留即成孤儿。不变量（单向子集，F240/F243/F246 同族反向）：注册页集 ⊆ 静态导航目标集 ∪ tabBar 页集；提取逻辑与 check-nav-targets.js 同款单一口径（query/${}截断取静态前缀，纯动态 url 计数不豁免断言，F212）；缺输入/注册集空/可达集空/断言败均 exit 1（F212 不放行）；npm run check:orphan-pages 接入 CI check job + Makefile check 链（orphan-pages-check，委托单一源，F250 guard-wiring 自动覆盖接线一致性）；摸底现状=零孤儿（11 注册页 ⊆ 10 静态目标 ∪ 4 tabBar 页，守卫先行防未来漂移，F231 同型）；变异三档实证（coupons 双导航入口改名 exit 1 精确拦 / app.json tabBar 移除 profile exit 1 精确拦 / mv 走 app.json 缺输入 exit 1，sed 反向还原后基线 exit 0，F231 铁律）；eslint 0err/0warn + jest 230 绿复验
- WXML事件绑定↔JS方法定义双源对账守卫（F252）：wxml 事件绑定（bindtap/catchtap/bindinput... 调用侧，散布模板）按名字引用同目录 js 中 Page/Component 的方法（声明侧），双源零断言——JS 方法改名/删除→wxml 绑定运行时静默失效（点击无反应），小程序无 tsc 编译期零拦截；check-mp-structure.js 只挡四件套齐全/tabBar 注册，绑定名↔方法集是它的盲区。不变量（单向子集，F240/F243/F246 同向）：wxml 静态事件绑定名集 ⊆ 同目录 js 可用方法集（Page 取 Page({}) 顶层键；Component 取 methods 块键）；动态绑定（值含{{}}）计数不拦，缺输入/绑定集空/断言败均 exit 1（F212 不放行）；npm run check:wxml-handlers 接入 CI check job + Makefile check 链（wxml-handlers-check，委托单一源）；变异三档实证（scan.wxml 绑定改名 exit 1 精确拦 / station-card Component methods 改名 exit 1 精确拦 / mv 走 payment.js 缺输入 exit 1，sed 反向还原后基线 exit 0，F231 铁律）；守卫首跑即撞出两处真实死绑定并修复：favorites 空态"去发现站点"按钮 onGoHome 无方法体=死按钮（补 wx.switchTab 回首页）+ index 地图 bindupdated="onMapUpdated" 引用不存在方法（死绑定移除）；基线实测 14 wxml / 63 静态绑定全对账通过；eslint 0err/0warn + jest 230 绿复验
- 导航目标↔页面注册双源对账守卫（F246）：运行时 wx.navigateTo/redirectTo/switchTab/reLaunch 的 url 字面量（调用侧，散布各页面）与 app.json pages 数组（声明侧，唯一注册源）双源零断言，任一侧单独变更即漂移——页面改名/移除注册→跳转运行时 "navigateTo:fail page is not found"；tabBar 页用 navigateTo/redirectTo 或非 tabBar 页用 switchTab→运行时 fail（F243 探测集↔声明集同族）。不变量（单向子集，F240/F243 同向）：静态导航目标集 ⊆ 注册页集；switchTab 目标 ∈ tabBar 页集、navigateTo/redirectTo 目标 ∉ tabBar 页集（reLaunch 只查子集）；check-mp-structure.js 只挡注册四件套齐全/tabBar 引用已注册页，调用侧字面量是它的盲区。提取含模板字符串，query/插值截断取静态前缀，纯动态 url 计数不拦；缺输入/注册集空/目标集空/断言败均 exit 1（F212 不放行）；npm run check:nav-targets 接入 CI check job + Makefile check 链（nav-targets-check，委托单一源）；变异四档实证（app.json 移除 coupons 注册 exit 1 双调用点精确拦 / profile.js 跳转目标改名 exit 1 / mv 走 app.json 缺输入 exit 1 / switchTab→navigateTo 撞 tabBar 页 exit 1，sed 反向还原后基线 exit 0，F231/F238 铁律禁 git checkout）；接手花絮：并发轮脚本撞 eslint 4 errors（generator-star-spacing×2 + max-depth 嵌套5>4×2）→提取逻辑抽 helper 函数降深+星号位置修正，重构后基线+变异复验全中；eslint 0err/0warn + jest 230 绿复验；基线实测 18 个静态跳转目标 ⊆ 11 个注册页

### Added
- auth 存储键双源对账守卫（F240）：scripts/check-auth-keys.js — 'token'/'userInfo' 存储键名在 app.js（boot 恢复读侧）与 services/api.js（登录写入侧）双源硬编码字面量且零断言，任一侧整侧改名→ boot 恢复读旧键静默落空→用户持有有效 token 却被静默登出（F224 双源漂移同族；eslint 守卫 F214 只挡认证层外直读写，层内双源漂移不设防；app.js 无测试文件，往返路径零覆盖）。不变量：keys(app.js) ⊆ keys(api.js)，提取 wx.get/set/removeStorage(Sync) 首参字面量+异步对象形态 key 属性（与 F214 selector 双形态对齐）；npm run check:auth-keys 接入 CI check job + Makefile check 链（auth-keys-check，委托单一源）；变异三档实证（api.js 整侧 token 改名 exit 1 / app.js 整侧 userInfo 改名 exit 1 / api.js 缺输入 exit 1，sed 反向还原后基线 exit 0；F231/F238 铁律：变异还原禁 git checkout）；eslint 0err/0warn + jest 230 绿复验；花絮：首版变异档只改 api.js 单处未拦住——单边部分改名=文件内部自相矛盾（api.test.js 领地），整侧改名才是双源漂移语义，变异档设计须对齐守卫的真实漂移场景

### Added
- userInfo 本地访问器补齐 + globalData.userInfo 裸字段守卫扩展（F239）：token 侧有 app.getToken()（globalData+storage 兜底）而 userInfo 侧无同构访问器=同型半边缺口——冷启动 onLaunch 走 api.getUserInfo() 异步回填，请求未回/失败时 globalData.userInfo 为空，页面直读=空态。修法：app.js 补 app.getUserInfo()（与 getToken 同构：globalData || getStorageSync('userInfo')）；迁移全仓唯一直读点 pages/profile/profile.js（loadUserInfo）；eslint 守卫③ selector 由 property.name='token' 扩为 /^(token|userInfo)$/（与既有守卫同块声明，F214 flat config 教训）；前置核验迁移后 pages/components/utils 零违规、ignores 并集未变=零行为变化；变异探针实证（globalData.userInfo+token 双注入 exit 1 精确报错 / 清理后 exit 0）；eslint 0err/0warn + jest 230 绿复验

### Added
- eslint 登录入口单一源架构守卫（F233）：no-restricted-syntax 新增 selector（wx.login 精确匹配 property.name）——登录必须走 app.login() 统一入口（token 落盘 setStorageSync+globalData 双写 + code 兑换 api.login），页面直调绕过统一落盘=半登录态漂移（F208/F214 架构守卫同族第⑤条）；与既有守卫**同块声明**（flat config 同 rule id 后块覆盖不合并）；摸底全仓仅 app.js:47 一处且 app.js 已在 ignores 并集内=零行为变化（F220 预防式门控：零违规先行）；变异三档实证（profile 页注入 wx.login exit 1 精确报错 / 清理后全仓 exit 0 / 基线 0）；eslint 0err/0warn + jest 230 绿复验

### Added
- eslint 端点地址单一源架构守卫（F227）：no-restricted-syntax 新增 2 条 selector（Literal + TemplateElement 首段）——运行时代码禁硬编码 http(s) URL 字面量，端点地址仅允许在 config/index.js 声明（环境切换单一源，F224 双源漂移同族缺口）；与 F208/F214 守卫**同块声明**（flat config 同 rule id 后块覆盖不合并）；ignores 并集新增 config/**（权威源）+ 测试文件（jest 断言 config 值/样例 URL 为合法用途，前置核验对既有①②③守卫零行为变化）；scan.js 注释内 URL 不参与 AST 零误伤；变异三档实证（Literal 注入 exit 1 精确报错 / 模板字符串注入 exit 1 / 清理后全仓 exit 0）；eslint 0err/0warn + jest 230 绿复验

### Added
- eslint 运行时日志守卫（F220）：小程序运行时代码（app.js/config/components/pages/services/utils）启用 no-console（allow: warn/error）——console.log/info/debug 残留污染微信开发者工具控制台且可能泄露订单/位置/充电会话等敏感字段；既有 catch 块 console.error 17 处实测放行；scripts/（CLI 合法输出）不在 files 内天然豁免 + 测试文件（jest/node 环境）显式豁免；变异三档实证（pages 注入 log+debug 全拦精确报错 / scripts 注入 log 零误伤 / 清理后全仓 exit 0）；eslint 0err/0warn + jest 230 绿复验
- eslint 架构守卫扩展（F214）：敏感凭据 storage 键（'token'/'userInfo'）仅认证层（app.js/services/api.js）可读写 + 禁直读 globalData.token 裸字段（须走 app.getToken()，含 storage 兜底逻辑）；3 条新 no-restricted-syntax selector（sync/async storage 形态 + MemberExpression 链）与 F208 守卫**同块声明**——flat config 同 rule id 后块覆盖前块不合并，分块声明前条会静默失效（调试实测，教训固化）；ignores 取豁免并集（app.js+api.js），前置核验两文件零违规、页面私有键（scanHistory/station_filter）零误伤；pages/profile 直读 globalData.token 改走 app.getToken()；变异测试实证（6 类违规注入全拦 exit 1 / F208 合并块回归仍触发 / 非敏感键零误伤 / 清理后 exit 0）；eslint 0err/0warn + jest 230 绿复验
- eslint 架构守卫（F208）：no-restricted-syntax 禁页面/组件直连 wx.request，HTTP 必须走 services/api.js 统一封装（防绕过 baseURL/token 注入/统一错误处理/401 登出）；AST 级精确匹配 property.name='request'，wx.requestPayment/wx.uploadFile 不误伤（grep 前缀匹配会误报——payment.js 的 wx.requestPayment 即实例，守卫用 AST 规避）；变异测试三档实证（注入违规 exit 1/清理后 exit 0/全仓复验 exit 0）；jest 230 绿复验

### Changed
- CI 健壮性补齐（F193/F199 模式例行体检落地本仓）：ci.yml 两 job 补 timeout-minutes（check=15 / structure=10，此前挂死最多吃满 GitHub 默认 6h runner）+ 新增 concurrency（cancel-in-progress，push/PR 并发跑批自动取消旧跑）；YAML 解析+结构断言校验（timeout/concurrency/原有 steps 全实测确认）；同轮摸底发现 jest 有 collectCoverageFrom 但无 coverageThreshold（覆盖率回退无声通过，F201 同型缺口），留测试维度轮按 F201 协议处理

### Added
- eslint 新增 78 条防回归规则（第六批，累计质量规则 63→141）：ESLint 核心规则全量扫描 — builtin 292 条去掉 recommended/已启用后 166 候选一次性临时入 config 实测，95 条 0 违规；剔除 7 条已废弃（no-catch-shadow / no-native-reassign / no-negated-in-lhs / no-new-symbol / no-spaced-func / lines-around-directive / id-blacklist）、9 条无选项即空转（no-restricted-* ×6 / id-denylist / id-match / jsx-quotes 无 JSX）、no-warning-comments（防 TODO 摩擦）、no-undefined（实测 34 违规），收 78 条：no-shadow / no-await-in-loop / complexity / max-depth / default-param-last / logical-assignment-operators / prefer-object-has-own / prefer-promise-reject-errors / semi / linebreak-style / unicode-bom 等；eslint exit 0 + jest 230 绿复验
- eslint 新增 20 条质量防回归规则（第五批）：no-labels / no-div-regex / accessor-pairs / no-nested-ternary / no-new-require / no-octal-escape / no-void / no-iterator / prefer-spread / prefer-rest-params / no-object-constructor / no-new-object / dot-notation / no-extend-native / no-return-await / symbol-description / no-duplicate-imports / no-useless-constructor / no-bitwise / no-param-reassign；候选池 24 条先全仓扫描实测（camelcase 46 / prefer-template 6 / no-confusing-arrow 3 违规剔除，no-with 与 recommended 重复剔除），0 违规 20 条全收。累计质量规则 43→63
- eslint 新增 11 条质量防回归规则（第二批）：no-implicit-coercion / no-empty-function / no-unneeded-ternary / no-lonely-if / prefer-object-spread / no-useless-computed-key / no-dupe-else-if / default-case / no-alert / no-multi-str / yoda；加入时全仓 0 违规（util.js padZero 隐式拼接顺手修复；notifications.js fire-and-forget catch 显式 disable+注释）
- eslint 新增 12 条质量防回归规则（第三批）：no-template-curly-in-string / no-unmodified-loop-condition / array-callback-return / no-useless-call / no-useless-concat / no-else-return / no-promise-executor-return / no-unsafe-optional-chaining / no-case-declarations / no-sequences / no-new-wrappers / prefer-regex-literals；加入时全仓 0 违规（测试文件 4 处 executor-return 顺手修为块体）。累计质量规则 19→31
- eslint 新增 12 条质量防回归规则（第四批）：no-throw-literal / no-irregular-whitespace / no-unreachable-loop / no-unused-expressions / require-await / no-multi-assign / no-extra-bind / no-useless-rename / no-array-constructor / prefer-numeric-literals / no-proto / no-new-func；加入时全仓 0 违规。累计质量规则 31→43
- eslint 启用 reportUnusedDisableDirectives=error：失效 disable 注释直接报错，防规则名笔误/规则删除后静默失效；加入时全仓 0 处失效
- CHANGELOG 清理：移除 Unreleased 段重复的第二批条目（F163 补回时误留的重复行）

### Changed
- lint 调用点单一源收敛（F195）：实测撞出 `npm run lint` 缺 `--max-warnings 0`（本地过 CI 红的门限漂移）→ package.json lint 补齐阈值，Makefile lint / scripts/lint-ci.js / CI ci.yml 三处全部委托 `npm run lint`（四处调用点归一）；变异测试实证门限有效（临时注入 no-var/no-unused-vars 违规 → exit 1 正确拦截，清理后 exit 0），lint:ci 全过 + jest 230 绿复验
- eslint 配置卫生去重（F189）：移除 22 条与 `js.configs.recommended` 完全重复的规则声明（no-undef / no-redeclare / no-dupe-keys / no-debugger / no-duplicate-case / no-prototype-builtins / no-self-assign / no-shadow-restricted-names / no-sparse-arrays / no-unreachable / no-useless-escape / no-misleading-character-class / no-async-promise-executor / no-class-assign / no-const-assign / no-this-before-super / require-yield / no-fallthrough / no-dupe-else-if / no-unsafe-optional-chaining / no-case-declarations / no-irregular-whitespace）；带选项覆盖的 no-unused-vars（argsIgnorePattern）/ no-constant-condition（checkLoops:false）保留；`--print-config` 前后逐条 diff = 零变化，eslint exit 0 + jest 230 绿 + lint:ci 全过复验

### Fixed
- `scan.wxml` 引用缺失的 `/assets/icons/scan-big.png` → 替换为 emoji 占位图标（F87）
- 6 处页面死链导航修复（F70：navigateBack/navigateTo 缺 fallback）

### 待办
- 真 appid 替换（当前占位符，待丁哥）
- 腾讯地图 MAP_KEY 配置
- 头像昵称 `<button open-type="chooseAvatar">` 采集方案
- api.js 错误路径分支覆盖补强（当前 branch 78.57%，实测 2026-08-04；旧记录 69.6% 已过期）
- scan-big.png 正式图标替换（当前 emoji 占位）

## [1.1.0] - 2026-07-31

### Added
- 部署门控脚本 `npm run deploy` / `deploy:check`（scripts/deploy.js）：结构门控→appid校验→密钥校验→miniprogram-ci 上传体验版，分级退出码（0/1/2/3），`--check` 干跑验证管线
- 部署脚本行为测试 ×3（门控先行 / appid占位拦截 / 参数校验），测试总数 215→218
- `.gitignore` 补 `private-key/`（代码上传密钥不落库）
- README 补「部署与发布」段 + 命令表

### 已知阻塞
- 真 appid + 上传密钥待丁哥；就位前 `deploy:check` 止步于 appid 校验（设计内拦截）

## [1.0.0] - 2026-07-31

### Fixed
- 上传包瘦身：`packOptions.ignore` 补 dir×2 + regexp×1 + file×3（lockfile 单项 160K），开发产物不再进微信上传包
- 移除 `app.js` 废弃 API `wx.getSystemInfoSync`（2.20.1+ 废弃，且零消费方）
- `profile.js` 移除废弃 API `wx.getUserProfile`（2.27.1+ 废弃，返回匿名"微信用户"会污染服务端资料），改静默登录
- 修复 jest 并行跑 worker 泄漏：cache TTL 真实定时器 suite 结束未清
- 移除误提交的 `coverage/` 产物，补 `.gitignore`

### Added
- ESLint 10 flat config 门控（`npm run lint`，0 错 0 警），修 20 处历史问题
- 小程序结构构建门控 `npm run check`：JSON 合法性 / 页面四件套 / tabBar 图标 / 组件引用解析
- 补齐 tabBar 缺失图标 ×8
- Jest 测试体系：8 套件 215 用例全绿，覆盖率 92.9%（services/utils/config）

### Changed
- B3 真 API 对齐：充电/订单/优惠券/积分全量接 `/business` 经营域
- 登录改 OAuth2 form-urlencoded；新增 snake→camel 归一化层（mapOrder/mapCoupon/mapPoints/mapPagination），UI 不再直碰后端字段
- 33 条契约测试锁定前后端字段映射

## [0.2.0] - 2026-07-02

### Changed
- API 配置对齐 `/api/v1/` 前缀

## [0.1.0] - 2026-06-23

### Added
- P1 首版：充电、支付、订单、地图、实时监控
