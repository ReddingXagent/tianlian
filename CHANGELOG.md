# Changelog — tianlian-user-mp

格式参考 Keep a Changelog。本仓为微信小程序用户端。

## [Unreleased]

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
