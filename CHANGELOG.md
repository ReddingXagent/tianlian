# Changelog — tianlian-user-mp

格式参考 Keep a Changelog。本仓为微信小程序用户端。

## [Unreleased]

### Fixed
- `scan.wxml` 引用缺失的 `/assets/icons/scan-big.png` → 替换为 emoji 占位图标（F87）
- 6 处页面死链导航修复（F70：navigateBack/navigateTo 缺 fallback）

### 待办
- 真 appid 替换（当前占位符，待丁哥）
- 腾讯地图 MAP_KEY 配置
- 头像昵称 `<button open-type="chooseAvatar">` 采集方案
- api.js 错误路径分支覆盖补强（当前 branch 69.6%）
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
