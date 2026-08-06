# 天链充电 · 用户小程序 (tianlian-user-mp)

天链V3 充电平台的**微信原生小程序**用户端：扫码充电、站点查找、订单/支付、优惠券/积分/钱包。

- 后端 API：天链V3 云端 `/api/v1`（云端由大圣维护，本仓只消费接口）
- 形态：微信小程序原生（WXML/WXSS/JS），无框架依赖，微信开发者工具直接打开即用

## 快速开始

1. 安装依赖：`npm install`
2. 用**微信开发者工具**打开本目录（需 `project.config.json`）
3. 本地联调：起云端 dev 或 cloud-mock（见 `tianlian-shared/cloud-mock`），`config/index.js` 默认 dev → `http://localhost:8000/api/v1`

## 常用命令

| 命令 | 作用 |
|------|------|
| `npm run check` | 小程序结构门控（JSON 合法性 / 页面四件套 / tabBar 图标 / 组件引用解析），错误退 1 |
| `npm test` | Jest 单测（9 套件 / 230 用例，覆盖率 98.07%） |
| `npm run lint` | ESLint flat config 门控（0 错 0 警） |
| `npm run deploy:check` | 部署管线就绪验证（门控→appid→密钥，不上传） |
| `npm run deploy` | miniprogram-ci 上传体验版（需真 appid + 密钥） |

> 微信小程序无 CLI 构建，`npm run check` 即 CI 构建替代；提交前三件套：`check` + `test` + `lint`。

## 目录结构

```
app.js / app.json / app.wxss   入口与全局配置（tabBar/权限/隐私接口声明）
pages/            11 个页面：index(首页) scan(扫码) charging(充电中)
                  orders/order-detail payment profile
                  coupons points favorites notifications
components/       empty / loading / station-card
services/api.js   唯一 API 层：request 封装 + snake→camel 归一化 + 全业务域方法
utils/            cache(TTL缓存) polling(轮询) perf(性能打点) util
config/index.js   环境配置（dev/staging/prod 切换 + 超时/轮询/缓存TTL）
scripts/          check-mp-structure.js 结构门控 / deploy.js 部署门控(miniprogram-ci)
```

## 环境与配置（config/index.js）

| 环境 | API_BASE_URL | 触发 |
|------|--------------|------|
| dev | `http://localhost:8000/api/v1` | 默认（`NODE_ENV !== production`） |
| staging | `http://8.134.106.166:8000/api/v1` | 手动切 ENV |
| prod | `http://8.134.106.166/api/v1` | `NODE_ENV=production` |

登录走 OAuth2 form-urlencoded（`/auth/login`），响应信封 `{code, data:{token,user}}`；token 存 storage，401/code=401 触发 `TOKEN_EXPIRED` 清理。

## API 层能力（services/api.js）

认证（login/wxLogin/logout/用户资料）· 站点（列表/附近/详情/搜索/筛选）· 收藏 · 充电（启动/状态轮询/停止）· 订单（列表/详情/评价）· 支付（创建/查询）· 钱包（余额/充值/流水）· 优惠券（列表/领取）· 积分（明细/签到）。所有后端 snake_case 字段经归一化层转 camelCase，UI 侧不直接碰后端字段名。

## 质量现状

- 测试：230 全绿，coverage 98.07%（Stmts 98.07% / Branch 85.76% / Funcs 98.33% / Lines 98.91%）
- lint：ESLint 10 flat config，0 错 0 警
- 对账守卫族：十七枚自动守卫全接 CI check job + Makefile check 链——导航↔注册（F246）/wxml绑定↔方法（F252）/auth键（F240）/死handler（F264）/孤儿页（F258）/孤儿组件（F284）/storage键（F270）/隐私API↔声明（F277）/请求单一源（F292）/setData性能反模式（F298）/wxs视图层隔离（F305）/JSON配置键白名单（F311）/setData负载体积（F317）/组件properties↔使用属性（F323）/组件事件triggerEvent↔绑定（F329）/原生组件属性域image·button·input·text·view·map白名单+枚举值域（F337→F344→F350→F356）/CSS变量死代码检测（F373）
- 上传包：主包 ~704K（≪2MB 限额），packOptions.ignore 已排除开发产物
- 合规：`lazyCodeLoading` / `requiredPrivateInfos` / `permission` 声明齐全；废弃 API（`wx.getSystemInfoSync` / `wx.getUserProfile`）已清零

## 部署与发布

微信小程序发布走 **miniprogram-ci 上传体验版 → 公众平台提交审核** 链路，脚本 `scripts/deploy.js`：

1. **结构门控**（复用 `check-mp-structure.js`，失败即中止）
2. **appid 校验**：占位符 `wx0000000000000000` 直接拦截（退 2）
3. **密钥校验**：`private-key/<appid>.key`（小程序后台→开发设置→生成代码上传密钥，已 gitignore），或 `MP_KEY_PATH` 环境变量
4. **上传**：`--check` 模式在第 3 步后止步；正式上传参数 `--version=` / `--robot=` / `--desc=`（默认取 package.json 版本 + git 分支@SHA）

退出码：0=成功/就绪 · 1=门控失败/运行错误 · 2=appid 占位 · 3=缺密钥。当前 appid 为占位符，`deploy:check` 会停在第 2 步——真 appid 待丁哥提供后即可贯通。

## 已知限制 / TODO

- `project.config.json` appid 为占位符 `wx0000000000000000`，上架需真 appid（待丁哥）
- `MAP_KEY` 为占位符，腾讯地图 key 待配
- cloud-mock 登录接口尚未对齐 OAuth2 form + 信封格式，本地登录全链路待通（云端配合走大圣）
- 头像昵称采集待 `<button open-type="chooseAvatar">` 组件方案（废弃 API 已清，UI 待排期）
- api.js 分支覆盖 78.57%（实测 2026-08-05），错误路径待补强
