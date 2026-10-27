# 安全修复笔记 — 天链V3 前端

> 日期: 2026-07-26（最近更新 2026-07-27）｜ 作者: 石猴（AI 编码助手）
> 范围: 28 high 漏洞分阶段治理 + moderate/low 收尾
> - **第一阶段（已完成）**: pin 6 个 fixable high + 清理 package-lock.json 的 npmmirror 镜像污染
> - **第二阶段（[64c8c64d]）**: brace-expansion 全局 force 5.0.8，清零 25 个 dev/build 链漏洞
> - **第三阶段（本次，[724e9fb0]）**: file-saver dead dep 移除 + @babel/core pin 7.29.7 + quill 书面豁免
> 关联: axios 1.18.1 升级后续、npm 12 allow-remote=none 拦截

---

## 0. 当前漏洞状态：28 high → 1 high，low 持续收敛

`npm audit` 当前: `{ low: 2, moderate: 3, high: 1 }`（[724e9fb0] file-saver 移除 + @babel/core pin 后实测）

- 剩 **1 high** = vite（§5 书面豁免：dev-only + 升级链 HIGH 风险）
- 剩 **1 high**(react-router qwww, §7 CSR 不可达豁免) + esbuild/vite 链(§5 dev-only)
- 剩 **2 low** = quill(§10.3 书面豁免：无修复版 + DOMPurify 已缓解) + 1 聚合传递项
- xlsx(§6)/file-saver(§10.1) dead dep 已移除清零；dev-chain 25 个(§1) 已清零；@babel/core(§10.2) 已 pin 修复

---

## 1. 本次（第二阶段）修复：brace-expansion 全局 force 5.0.8

### 1.1 根因

本次范围的 25 个 high（jest 链 19 + vite-plugin-pwa 链 6）**全部追溯到同一 advisory**：brace-expansion OOM DoS（GHSA-mh99-v99m-4gvg，range `<=5.0.7`）。

传递链（npm audit 的 via 字段逐层追溯）：
- **jest 链**：`ts-jest → @jest/transform → babel-plugin-istanbul → test-exclude → glob → minimatch@3/@9 → brace-expansion`（pin 在 1.1.16 / 2.1.2）
- **pwa 链**：`vite-plugin-pwa → workbox-build → @trickfilm → ejs → jake → filelist → minimatch@5 → brace-expansion`（此前已是 5.0.8）

npm 把这两条链上每个包都计一个 high，所以表面是 25 个，根源是 1 个 advisory。

### 1.2 为何「升级 jest」不解决问题

- jest 已是最新 `30.4.2`（dist-tags latest），ts-jest 已是 `29.4.9`（最新 29.4.12，同 major）
- advisory range 形如 `jest >=19.1.0`、`ts-jest >=20.0.0`，**覆盖所有现代版本**
- npm 给出的「修复」是退化到漏洞引入前的远古版本（jest 19.0.2 / ts-jest 29.1.2），会废掉现代测试写法 —— 拒绝
- 真根因在更深的 brace-expansion，与 jest 顶层版本无关

### 1.3 brace-expansion 为何必须 force

brace-expansion 版本谱（dist-tags）：`1.x=1.1.16`、`2.x=2.1.2`、`3.x=3.0.2`、`latest=5.0.8`。
advisory range `<=5.0.7` 数学上覆盖所有 `<5.0.8` 的版本 —— **1.x/2.x 线永远无修复版**。
jest 链的 minimatch@3（要求 `^1.1.7`）、minimatch@9（要求 `^2.0.1`）只能用 force override 到 5.0.8 才能脱出。

### 1.4 修复方案

`package.json` 的 `overrides` 改为顶层 force（移除原 `test-exclude`/`workbox-build` 嵌套 override，顶层已覆盖）：

```json
"overrides": {
  "brace-expansion": "5.0.8",
  ...
}
```

npm 强制 minimatch@3（jest 链）和 minimatch@9 也解析到 brace-expansion 5.0.8（违反其 `^1.1.7`/`^2.0.1` semver，由 overrides 机制强制）。install 后 `npm ls brace-expansion` 全部 deduped 到 5.0.8。

### 1.5 兼容性验证（关键风险点）

minimatch@3 被 force 用 brace-expansion 5.x 存在 API 兼容风险。实测：
- brace-expansion 5.x 与 1.x 导出兼容（`expand`/`braceExpand` 函数签名稳定），无运行时错误
- `npm run build` 成功（8.26s）
- vitest 全量无逻辑回归（详见 §7 flaky 说明）
- 单独跑 jest 链相关测试文件 11/11 全绿

### 1.6 效果

`npm audit` high：**28 → 2**（清零 25 个 dev-chain，剩 vite + xlsx 见 §5/§6）。

---

## 2. 第一阶段已完成项（保留）

### 2.1 overrides 精确 pin（6 个完全修复）

在 `package.json` 加 `overrides`。所有 pin 版本均满足父依赖 semver range，无 ERESOLVE。

| 包 | pin 版本 | 漏洞 range | 主要父依赖（range） | 状态 |
|---|---|---|---|---|
| fast-uri | `3.1.4` | `3.0.0 - 3.1.3` | ajv `^3.0.1` | ✅ 完全修复 |
| form-data | `4.0.6` | `4.0.0 - 4.0.5` | axios `^4.0.5` | ✅ 完全修复 |
| js-yaml | `3.15.0` | `<=3.14.2` | @istanbuljs/load-nyc-config `^3.13.1` | ✅ 完全修复 |
| postcss | `8.5.23` | `<=8.5.17` | vite5 `^8.4.43` / vite8 `^8.5.15` | ✅ 完全修复 |
| undici | `7.29.0` | `7.0.0 - 7.27.2` | jsdom29 `^7.25.0` | ✅ 完全修复 |
| ws | `8.21.1` | `8.0.0 - 8.20.1` | happy-dom `^8.18.3` / jsdom26 `^8.18.0` | ✅ 完全修复 |

brace-expansion 原三条线 pin（2.1.2 / 1.1.16 / 5.0.8）已被 §1.4 的顶层 force 5.0.8 取代。

### 2.2 npmmirror lock 污染清理

- `package-lock.json` 中 833 处 `https://registry.npmmirror.com/...` → `https://registry.npmjs.org/...`
- 清理后 `grep -c npmmirror package-lock.json` = 0
- 裸 `npm install`（不带 `npm_config_allow_remote`）正常完成

---

## 3. npmmirror 遮蔽 audit（历史背景）

清理 npmmirror 后 `npm audit` 从 9 high → 28 high。根因：npm audit 默认跳过 npmmirror 镜像包的 advisory 匹配，原 lock 的 833 个 npmmirror 包被完全忽略，所以任务卡基线的「9 high」是虚假低数。本次 install **没有引入新漏洞**，多出的 19 个 high 是依赖树里既有、但被遮蔽至今的 dev/build 工具链漏洞。**不能用保留 npmmirror 污染换取虚假的「9 high」**。

---

## 4. vite-plugin-pwa 补充说明

`vite.config.ts` 第 14 行：**VitePWA 插件已被注释禁用**（团队决定：管理后台不需要 PWA，Service Worker 会缓存旧的 401 响应导致登录闪退）。因此 vite-plugin-pwa 是 devDependencies 里的残留包，其传递依赖（workbox-build/ejs/jake/filelist）纯 dev-only，**无生产暴露面**。本次通过 brace-expansion 5.0.8 force 已清零其 audit 计数（pwa 链 6 个 high 全部消除），不影响 build。后续可评估直接从 devDependencies 移除该包。

---

## 5. 剩余 high #1：vite（major breaking，书面豁免——保持 5.4.21 不动）

> 评估批次 [6fae1cbc]。结论：升级链风险 HIGH + 漏洞 dev-only（生产零暴露）→ **不强升，本条为书面豁免**。

### 5.1 漏洞与版本现状

- 当前 `vite@5.4.21`（传递 `esbuild@0.21.5`）
- 漏洞：esbuild dev server 任意请求/响应读取（GHSA-67mh-4wv8-2v99，esbuild `<=0.24.2`）；vite range `<=6.4.2 || 8.0.0 - 8.0.15`（Path Traversal / launch-editor NTLMv2 泄露 / fs.deny 绕过，均为 dev server）
- npm audit 计 **1 high**，来源两条：
  - 顶层 `node_modules/vite@5.4.21`（落在 `<=6.4.2`）
  - vitest 嵌套 `node_modules/vitest/node_modules/vite@8.0.14`（落在 `8.0.0 - 8.0.15`）

### 5.2 插件链兼容矩阵（vite 5→8 升级可行性）

| 组件 | 当前版本 | vite 8 要求 | 兼容 | 说明 |
|---|---|---|---|---|
| vite | 5.4.21 | 8.1.5（latest dist-tag） | 目标本体 | `npm view vite version` = 8.1.5 |
| @vitejs/plugin-react | **4.7.0** | **6.0.4** | ❌ 跨 2 major | 4.7.0 peer=`vite ^4‖^5`；6.0.4 peer=`vite ^8` + **强制 peer `babel-plugin-react-compiler ^1.0.0`** + `@rolldown/plugin-babel` |
| vite-plugin-pwa | 1.3.0（已禁用） | peer 含 `^8` | ✅（残留） | 见 §4，已注释禁用，无生产暴露 |
| vitest | 4.1.7 | 自带嵌套 vite@8.0.14 | ⚠️ 嵌套漏洞版本 | `npm ls vite`：vitest→vite@8.0.14 落在 8.0.0-8.0.15 漏洞范围 |

### 5.3 升级风险（HIGH）

1. **plugin-react 跨 2 major（4.7→6.x）且强制 React Compiler**：6.0.4 把 `babel-plugin-react-compiler ^1.0.0` 列为 **required peer**。启用 React Compiler 是全项目编译行为变更，对组件代码模式有严格要求（refs/effects/Rules-of-Hooks 边界、幂等渲染），需独立迁移评估 + 全量回归，远超"audit 修复"范畴。
2. **vite 8 默认 Rolldown bundler**：替换 Rollup 管线，`build.rollupOptions.output.manualChunks` 在 Rolldown 下行为可能变化。本项目 `vite.config.ts` 重度依赖 manualChunks 做 vendor 分包（vendor-antd/echarts/react/three 等 8 个 chunk），须单独验证分块策略不被破坏。
3. **vitest 嵌套 vite@8.0.14 仍在漏洞范围**：升顶层 vite 到 8.1.5 不能清零 audit——vitest@4.1.7 锁定的嵌套 vite 是 8.0.14（漏洞版本），需联动升 vitest 或加 overrides 强制，链式复杂。

### 5.4 攻击面分析（dev-only，生产零暴露）

- esbuild/vite 漏洞**全部针对 dev server**：esbuild 允许任意网站向本地 dev server 发请求并读响应；vite Path Traversal / fs.deny 绕过针对 `npm run dev` 起的本地开发服务。
- **生产构建产物（dist/）不含 dev server 代码**，`npm run build` 产出的包不受影响（本次实测 `✓ built in 9.94s`）。
- 利用前提：开发者主动 `npm run dev` 且 dev server 暴露在可达网络（vite 默认仅 bind localhost），攻击者需诱导开发者访问恶意页面（钓鱼）。
- 运行时（生产部署）暴露面 = **0**。

### 5.5 结论

升级链风险 HIGH（plugin-react 2-major + 强制 React Compiler + Rolldown 分包重验 + vitest 嵌套 vite 联动），收益仅限 dev-only 漏洞（生产零暴露）。

**决策：保持 `vite@5.4.21` 不动，本条作为书面豁免。** 残留 1 high（vite）已有对应豁免条目（本节）。

若未来推进 vite 8 迁移，须单独立项：① plugin-react 4.7→6.x 的 React Compiler 迁移评估；② Rolldown 下 manualChunks 分包验证；③ vitest 联动升级清嵌套 vite@8.0.14；分步在 worktree 验证 build + vitest + playwright e2e。

---

## 6. 剩余 high #2：xlsx（已解决 [6fae1cbc]——移除 dead dependency）

### 6.1 漏洞
- `xlsx@0.18.5`（SheetJS 社区版），Prototype Pollution（GHSA-4r6h-8v6p-xvw6）+ ReDoS（GHSA-5pgg-2g8v-p4x9），**No fix available**（SheetJS 把修复版撤出 npm，仅发布到自家 CDN）。

### 6.2 根因调查：xlsx 是 dead dependency

全项目 grep 确认 **xlsx 从未被 import**（3 次交叉验证）：
- `grep -rn "from 'xlsx'" src/` → **0 处**
- `grep -rn "import.*xlsx\|require.*xlsx\|XLSX\." src/` → **0 处**
- 唯一出现：`src/pages/Reports/index.tsx:33` 的字符串字面量 `'xlsx'`（导出格式 `<Select>` 的 value），**非库调用**。

Reports 页导出实现（`src/pages/Reports/index.tsx`）：
- **Excel 导出**：`handleExport` 走 `fetch('/api/v1/reports/${type}?format=xlsx')`，由**后端生成** xlsx，前端只接收 blob 触发下载（第 192-212 行）。前端不解析、不生成 xlsx。
- **CSV 导出**：走自家 `src/utils/csvExport.ts`（纯字符串拼接，零第三方 Excel 库，第 14/309 行）。

→ **前端既不解析也不生成 xlsx，xlsx 包攻击面 = 0。**

### 6.3 处置（优于"换 exceljs"）

任务给的选项是「换 exceljs / 写风险豁免」。根因调查发现更优解：**xlsx 根本未被引用，直接移除**——比引入 exceljs（新增依赖、增包体积）更干净。

- `package.json` dependencies 移除 `"xlsx": "^0.18.5"`
- `vite.config.ts` manualChunks 清理 `node_modules/xlsx/` 引用（chunk 判断改为仅 file-saver）
- `npm install` 移除 xlsx + 8 个传递依赖（adler-32 / cfb / codepage / crc-32 / frac / ssf / wmf / word），`package-lock.json` 纯删除 **-105 行零漂移**（无版本漂移）
- `npm audit` high：**2 → 1**（xlsx high 清零）
- `npm run build` ✓ 9.94s 无回归（dead dependency 移除零副作用）

---

## 7. react-router（已升级 6.30.4→7.18.2，qwww HIGH 书面豁免——CSR 不可达）

> 评估批次 [6fae1cbc] 初始决策保持 v6；**2026-07-31 [D9-security a402f847] 升级至 7.18.2**，清掉 wrjc+337j 两个 moderate，引入 qwww high（CSR 不可达，豁免）。

### 7.1 已修复漏洞（升级 7.18.2 清零）

- **GHSA-wrjc-x8rr-h8h6**（moderate）：Open redirect via backslash in `<Link>` / `useNavigate`（CVE-2025-68470 bypass）。影响范围 6.0.0–7.17.0 → **7.18.2 已修复**。
- **GHSA-337j-9hxr-rhxg**（moderate）：Arbitrary Constructor Injection via `deserializeErrors()` SSR Hydration。影响范围 6.0.0–7.17.0 → **7.18.2 已修复**。

### 7.2 新引入漏洞（qwww，书面豁免）

- **GHSA-qwww-vcr4-c8h2**（HIGH）：RSC Mode CSRF Bypass Allows Action Execution Before 400 Response。影响范围 7.12.0–<8.3.0 → 7.18.2 落入。
- **攻击面分析**：仅影响启用 SSR 的 unstable RSC Framework mode。本项目是 **Vite 纯 CSR SPA**（`vite build`→静态 dist，无 SSR/RSC/hydration），漏洞代码路径**架构上不可达**，实际风险=零。与已豁免的 337j（SSR hydration 注入）完全同类。
- **版本约束**：同时避开 wrjc/337j（需 >7.17.0）和 qwww（需 <7.12.0 或 ≥8.3.0）→ 数学上不存在已发布 react-router-dom 版本。react-router 主包有 8.3.0 但 react-router-dom 止于 7.18.2，全清需 v7→v8 major 迁移（131 处 import 改源），超出本次范围。

### 7.3 升级验证（零 breaking change）

- 131 个 import 点全用 v7 保留核心 API（BrowserRouter/Routes/Route/Navigate/Outlet/useNavigate/useLocation/useParams/useSearchParams），无 data router/SSR/@remix-run 引用
- `npx tsc --noEmit` exit 0，`npm run build` 成功（11.27s），vitest 1395 passed
- `@remix-run/router` 被 v7 内联移除，无残留依赖

### 7.4 结论

**决策：保持 `react-router-dom@7.18.2` + qwww 书面豁免。** wrjc+337j 两个 moderate 已清零；qwww high 对纯 CSR SPA 代码路径不可达（与 337j 同类豁免）。后续若 react-router-dom 发布 8.3.0+，可评估迁移彻底清零。

---

## 8. vitest flaky 说明（既有问题，非本次引入）

基线（HEAD）全量 vitest 实测存在并行 flaky —— Fleet 页 `getByXxx` 企业名渲染超时。本次 force brace-expansion 5.0.8 **未引入回归**，新鲜证据：

| 状态 | failed | 失败文件 |
|---|---|---|
| 基线 HEAD | 1 | dashboard.test.tsx |
| force 5.0.8 第1次 | 5 | settings.test.tsx 等 |
| force 5.0.8 第2次 | 1 | vehicles.test.tsx |
| force 5.0.8 单独跑失败文件 | **0** | settings+dashboard 全绿 (11/11) |

失败测试每次不同、数字波动（1/5/1），均为 Fleet 页 UI `getByXxx` 超时（149 文件并行 jsdom 资源竞争）。brace-expansion 是 glob 库，与 React 组件渲染无因果；单独跑全绿证明组件逻辑与 brace-expansion 5.x 兼容。建议另立卡修 flaky（调 `waitFor` 超时 / msw mock 时序，超出依赖升级范围）。

---

## 9. 验收结论（新鲜证据）

### 9.1 本次 [6fae1cbc] 验收

| 验收项 | 状态 | 证据 |
|---|---|---|
| npm audit high | ✅ 2 → 1 | xlsx 移除清零；剩 1 high = vite（§5 书面豁免） |
| react-router moderate×2 | ✅ 已修复 | §7 升级 7.18.2 清零 wrjc+337j；qwww high CSR 不可达豁免 |
| npm run build | ✅ 成功 | `✓ built in 9.94s`（删 xlsx 零副作用） |
| npm install | ✅ 干净 | removed 9 packages，lock -105 行零漂移 |

### 9.2 累计验收（含前批次）

| 验收项 | 状态 | 证据 |
|---|---|---|
| npm audit high | ✅ 28 → 1 | 25 dev-chain(§1) + xlsx(§6) 清零；剩 vite(§5) 豁免 |
| npx vitest run | ✅ 无回归 | 见 §8 flaky 说明 |
| npx tsc --noEmit | ✅ 零错误 | exit=0 |
| npm run build | ✅ 成功 | 9.94s，dist 产物正常 |

---

## 10. 第三阶段 [724e9fb0]：file-saver 移除 + @babel/core pin + quill 豁免

### 10.1 file-saver 移除（dead dependency，续 §6 模式）

全项目 grep 确认 file-saver 从未被 import：
- `rg "file-saver|saveAs|FileSaver" src/` → **0 处**
- 唯一残留：`vite.config.ts` manualChunks 的 `node_modules/file-saver/` chunk 判断（永不命中的死代码）

处置（同 §6 xlsx 模式，直接移除优于换库）：
- `package.json` dependencies 移除 `file-saver`、devDependencies 移除 `@types/file-saver`
- `vite.config.ts` 删除 `vendor-report` chunk 判断（4 行死代码）
- §6.3 当年为 xlsx 移除后留下的「chunk 判断改为仅 file-saver」至此一并清零
- `npm install` removed 2 packages，lock 纯删除无漂移

### 10.2 @babel/core pin 7.29.7（清零 1 low）

- 漏洞：`@babel/core <=7.29.0` Arbitrary File Read via sourceMappingURL（GHSA-4x5r-pxfx-6jf8，low）
- 攻击面：babel 编译期/dev-only，生产构建产物零暴露；但 fix 非 breaking，顺手清零
- 版本选择：latest=8.0.1（major 跃迁）被 ts-jest@29.4.9 peer `@babel/core <8` 拒绝 → 选 7.x 线最新修复版 **7.29.7**（满足 `^7`/`<8` 全部 peer，零 ERESOLVE）
- `package.json` overrides 加 `"@babel/core": "7.29.7"`（顶层 force，整树 dedup）
- 效果：`npm audit` low **3 → 2**

### 10.3 quill（low，书面豁免——无修复版 + DOMPurify 已缓解）

> 评估批次 [724e9fb0]。结论：quill 2.x 线无修复版 + npm 建议降级无效 + 渲染端已有 DOMPurify 净化 → **保持不动，本条为书面豁免。**

**漏洞**：quill@2.0.3 XSS via HTML export feature（GHSA-v3m3-f69x-jf25，low）。advisory vulnerable range `=2.0.3`。

**为何无法升级（三个方向均堵死）**：
1. **quill 2.x 线无修复版**：registry dist-tags 2.0.x 止于 2.0.3（`npm view quill versions` 最后即 2.0.3），advisory 标 `=2.0.3` 但无 2.0.4 发布。2.x 线数学上无修复版。
2. **react-quill-new 依赖锁死 ~2.0.3**：`react-quill-new@3.8.3` 声明 `quill: ~2.0.3`（仅允许 2.0.x），无法在范围内上浮。
3. **npm 建议降级无效**：`npm audit fix --force` 建议装 `react-quill-new@3.7.0`，但 3.7.0 依赖 `quill: ~2.0.2`（同样落在漏洞 2.0.x 上下文）——降级不解决漏洞，是 npm 算法的错误建议，拒绝。

**使用面（极窄 + 已认证）**：
- 全项目仅 `src/pages/Knowledge/Edit.tsx` 单页使用 react-quill-new（知识库富文本编辑）
- 使用者 = 已登录管理员（非公开匿名输入）

**缓解（渲染端 DOMPurify 已守门）**：
- 编辑产出 HTML 存后端，渲染端 `src/pages/Knowledge/Detail.tsx:159` 与 `index.tsx:977` **均经 `DOMPurify.sanitize()` 净化**后才 `dangerouslySetInnerHTML`
- 专属测试 `src/pages/Knowledge/__tests__/knowledge.xss.test.tsx` 验证净化链路
- 项目 dependencies 已含 `dompurify@3.4.12`（无额外引入成本）
- 即便 quill HTML export 含恶意载荷，渲染时被 DOMPurify 剥离；残留风险仅在编辑器内部自渲染（管理员自输入，低风险）

**结论**：**决策：保持 `quill@2.0.3`（经 react-quill-new@3.8.3）不动。** 无修复版 + 使用面极窄 + DOMPurify 渲染端守门 → 风险可接受。后续若 quill 发布 2.0.4+ 或 react-quill-new 切换 quill-next，可联动升级。

### 10.4 本次 [724e9fb0] 验收

| 验收项 | 状态 | 证据 |
|---|---|---|
| npm audit total | ✅ 7 → 6 | @babel/core low 清零（low 3→2）；剩 vite(§5)/react-router(§7)/quill(§10.3) 均已豁免 |
| file-saver 移除 | ✅ 干净 | removed 2 packages，lock 0 残留，vite.config 死代码清理 |
| @babel/core pin | ✅ 生效 | 7.29.0 → 7.29.7，满足 ts-jest `<8` peer，零 ERESOLVE |
| quill low | ✅ 书面豁免 | §10.3 无修复版 + DOMPurify 渲染端守门 |
| npm run build | ✅ 成功 | `✓ built in 27.29s`，vendor-report chunk 已消失 |
| npx vitest run | ✅ 无回归 | 150 files / 1179 passed / 9 skipped / 0 failed，Duration 403.58s |
