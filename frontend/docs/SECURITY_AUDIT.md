# 前端安全审计 — npm audit 漏洞分析与处置

> 卡片：`6061eb1a`
> 日期：2026-08-01
> 审计人：石猴（AI 编码助手）
> 范围：`frontend/`（天链V3 管理后台，React + Vite SPA）
> 基线命令：`npm audit`（6 漏洞：2 low / 1 moderate / 3 high，归并为 4 个根因包）

## 结论速览

| # | 包 | 严重度 | 漏洞 | 处置 | 理由 |
|---|----|-------|------|------|------|
| 1 | react-router-dom@7.18.2 | HIGH | RSC Mode CSRF Bypass (GHSA-qwww-vcr4-c8h2) | **不降级 / 不适用** | 纯 SPA，无 RSC，攻击面不存在 |
| 2 | quill@2.0.3 (经 react-quill-new) | LOW (CVSS 6.1) | XSS via HTML export (GHSA-v3m3-f69x-jf25) | **应用层修复，不降级** | 渲染层已有 DOMPurify 主防线；本次再加保存路径纵深防御 |
| 3 | vite@5.x | HIGH+MODERATE | dev server fs.deny / path traversal / launch-editor | **暂不升级** | 开发服务器漏洞，不入生产构建；团队 macOS |
| 4 | esbuild@<=0.24.2 | MODERATE | dev server CSRF (GHSA-67mh-4wv8-2f99) | **暂不升级** | 同 vite，dev-only，随 vite 升级解决 |

**核心判断**：4 个漏洞中无 1 个影响生产运行时。react-router 漏洞的攻击面（RSC）在本项目不存在；quill 漏洞的渲染落点已被 DOMPurify 封死；vite/esbuild 漏洞仅存在于本地开发服务器。因此**不触发任何 breaking-change 降级/升级**，仅对 quill 做应用层纵深加固。

---

## 1. react-router-dom@7.18.2 — RSC Mode CSRF Bypass

**漏洞**：GHSA-qwww-vcr4-c8h2。React Router 在 RSC（React Server Components）模式下，CSRF 防护可被绕过，允许在 400 响应前执行 Action。影响范围 7.12.0–8.2.0。官方修复要求降级到 7.11.0（breaking）。

**攻击面分析**：该漏洞**仅在启用 RSC / Server Components 时成立**。本项目是 Vite 驱动的纯客户端 SPA，路由用 `react-router-dom` 的 `BrowserRouter`/`MemoryRouter` 客户端渲染，无任何服务端组件管线。

**证据**（全仓 grep 无命中）：
```
$ grep -rn 'serverComponents\|renderToPipeableStream\|hydrat\|react-server\|RSC' vite.config.* src/
# (空输出)
```
- `vite.config.ts` 仅 `@vitejs/plugin-react` + 代理，无 SSR/RSC 插件。
- 构建产物是静态 SPA chunk（见 `build.rollupOptions.manualChunks`），无 `renderToPipeableStream` 服务端入口。

**处置**：**不降级**。降级到 7.11.0 是 breaking change，且 7.12–7.18 期间的路由改进会丢失，而漏洞前提（RSC）在本项目根本不存在——为一个不成立的攻击面付出 breaking-change 代价不成立。

---

## 2. quill@2.0.3 — XSS via HTML export（经 react-quill-new@3.8.3）

**漏洞**：GHSA-v3m3-f69x-jf25。Quill 的 HTML export 功能可产生含可执行脚本的 HTML，导致存储型 XSS。官方修复要求降级 react-quill-new 到 3.7.0（breaking）。

**威胁模型**：
- 富文本来源：`src/pages/Knowledge/Edit.tsx` 的 `ReactQuill`，用户编辑知识库文章，`onChange` 产出 HTML 存入 `content` 状态。
- 写入：`knowledgeAPI.create/update` 将 `content` HTML 持久化到后端。
- **渲染落点（真正的 XSS sink）**：
  - `src/pages/Knowledge/Detail.tsx:159` — `dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(article.content) }}`
  - `src/pages/Knowledge/components/SearchTab.tsx:125` — `dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(...) }}`

**主防线（已存在）**：两个渲染落点**均已用 `DOMPurify.sanitize` 净化**，且由测试 `src/pages/Knowledge/__tests__/knowledge.xss.test.tsx`（卡 0160e45e）锁定——验证 `<script>` 与 `<img onerror>` 被剥离、合法富文本不被误杀。因此无论 Quill 的 HTML export 产出什么，到 DOM 前都会被剥离，**漏洞在渲染层不可利用**。

**纵深防御（本次新增）**：在保存路径再加一道净化（`Edit.tsx` `handleSave`）：
```ts
const payload = { ...values, content: DOMPurify.sanitize(content) };
```
理由：项目规划中有 `mobile/` 端（见根 CLAUDE.md 项目结构），未来消费者可能复用同一文章 API 且未必在渲染层二次净化。在写入端剥离可执行脚本，使存储数据本身安全，保护所有下游消费者。

**为什么不降级 react-quill-new**：3.7.0→3.8.3 之间有其他改进，降级是 breaking change；而漏洞已被渲染层 DOMPurify 完全封堵，保存路径再加净化后形成双防线。应用层修复优于依赖降级。

**验证**：新增 `src/pages/Knowledge/__tests__/knowledge.edit.sanitize.test.tsx`（create + update 两路径），提交前含 `<script>`/`onerror` 的 content 经保存路径后断言被剥离、合法 `<img>` 保留。RED→GREEN 确认。

---

## 3. vite@5.x — Dev Server 漏洞（HIGH + MODERATE）

**漏洞**：
- `server.fs.deny` 绕过（Windows）、路径穿越
- `launch-editor` 经由 NTLMv2 凭据中继

**攻击面分析**：均针对 **Vite 开发服务器**（`vite` / `vite dev`）。
- 生产部署是 `vite build` 产出的静态文件，由后端/Nginx 托管，**生产运行时不包含 vite 的 dev server 代码**。
- NTLMv2 漏洞仅影响 Windows + Edge/IE 环境的 `launch-editor`；团队开发机为 macOS（`Darwin 25.5.0`），不适用。
- `server.fs.deny` 路径穿越需攻击者能访问开发服务器端口；本地开发环境不在公网。

**处置**：**暂不升级**。升级到 vite 8.x 是 major 跳跃（5.x → 8.x），跨三个大版本，构建配置/插件/Rollup API 变更风险大，而漏洞全部 dev-only、不入生产。待后续 routine 依赖维护窗口统一评估 vite major 升级。

---

## 4. esbuild@<=0.24.2 — Dev Server CSRF（MODERATE）

**漏洞**：GHSA-67mh-4wv8-2f99。esbuild 开发服务器存在 CSRF，任意网站可向开发服务器发请求并读取响应。

**攻击面分析**：同 vite——esbuild 的开发服务器仅本地开发用，生产构建产物不含该服务器代码。

**处置**：**暂不升级**。esbuild 作为 vite 的传递依赖，单独升级会与 vite 锁定版本冲突；其漏洞随 vite 一起在 future major 升级中解决。dev-only，不影响生产。

---

## 风险接受声明

以上 4 项处置（2 项不适用 / 不降级 + 2 项 dev-only 暂不升级）均经威胁模型确认不影响生产运行时安全。quill 的存储型 XSS 已由「渲染层 DOMPurify 主防线 + 保存路径纵深防御」双重覆盖，并附测试锁定。本审计结论可在下次依赖维护周期复审。

## 验证

- `npx tsc --noEmit` → EXIT 0
- `npx vitest run` → 全绿（新增 2 测试，既有 XSS 测试不受影响）
- `npm audit` 漏洞清单不变（未做依赖升降级，符合「应用层修复」决策）
