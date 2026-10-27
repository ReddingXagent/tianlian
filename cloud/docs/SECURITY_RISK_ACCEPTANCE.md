# 前端依赖安全风险接受记录

> 决策日期: 2026-07-31 ｜ 决策人: 大圣(技术选型自主拍板) ｜ 关联卡: D7/D9前端依赖安全(450d70f8)
> 背景: `npm audit --omit=dev` 报 4 漏洞(2 high + 2 low)，逐项评估后决定风险接受，不做大版本升级。

---

## 1. react-router RSC Mode CSRF (high×2)

- **Advisory**: [GHSA-qwww-vcr4-c8h2](https://github.com/advisories/GHSA-qwww-vcr4-c8h2)（2026-07-24 发布）
- **受影响区间**: react-router 7.12.0 – 8.2.0；修复版本仅 8.3.0+
- **当前版本**: react-router-dom ^7.18.2（在受影响区间内）

### 不可利用性结论

Advisory 明确该漏洞**仅影响 RSC / Framework 模式**（`createBrowserRouter` + loader/action 的服务端数据流）。我方用法：

- 纯客户端 SPA：`main.tsx` 使用 `BrowserRouter`，无 RSC、无 framework 模式、无 loader/action 服务端执行
- 全项目 grep 确认零 `unstable_*` RSC API 用法

⇒ CSRF vector 在我方架构下**不可达，不可利用**。

### 为何不升 8.3.0

react-router v8 起 `react-router-dom` 并入 `react-router`，且升级须连带 **React 18→19 + Vite 5→7** 两个红线级大版本（antd 5.29 兼容性、150 个测试文件全量回归）。收益（修复一个不可利用的 CVE）≪ 风险（两个大版本连锁回归面）。

- React 19 / Vite 7 升级另立预研卡（low）单独评估，不塞进安全卡。
- `npm audit fix --force` 会降级到 7.11.0（受影响区间外的最高版），属 breaking change 路径，**禁用**。

### 重新评估触发条件

- 我方引入 RSC / framework 模式（createBrowserRouter + loader/action 服务端流）→ 必须立即升 8.3.0+
- react-router 8.x 稳定且 React 19/Vite 7 预研完成 → 随大升级一并迁移

---

## 2. quill XSS via HTML export (low×2)

- **现状**: quill 2.0.3 = npm 上游最新版，**无官方补丁**；react-quill-new 已升至 ^3.8.3（其依赖的 quill 仍是 2.0.3）

### 缓解措施（已落地）

- 全项目仅 2 个 `dangerouslySetInnerHTML` 渲染点，**全部经 `DOMPurify.sanitize`**：
  - `src/pages/knowledge/Detail.tsx:159`
  - `src/components/knowledge/SearchTab.tsx:124`
- 已有专门 XSS 回归测试：`src/pages/knowledge/knowledge.xss.test.tsx`

⇒ 渲染侧 DOMPurify 完全中和该 XSS vector，**不可利用 → 风险接受**。

### 重新评估触发条件

- quill 上游发布 >2.0.3 补丁版 → 升级
- 新增 HTML 富文本渲染点 → 必须过 DOMPurify + 补回归测试

---

## 复核快照（2026-09-01，卡 fcfe05f0）

- `npm view quill versions`: 上游最新仍为 **2.0.3，无补丁版发布** ⇒ 维持豁免，不 force
- 缓解点复核（3 处 sanitize 全部在位）:
  - `src/pages/Knowledge/Detail.tsx:159`（dangerouslySetInnerHTML → DOMPurify.sanitize）
  - `src/pages/Knowledge/components/SearchTab.tsx:125`（同上）
  - `src/pages/Knowledge/Edit.tsx:120`（提交侧预净化，纵深防御）
- XSS 回归测试: `knowledge.xss.test.tsx` + `knowledge.edit.sanitize.test.tsx` → 4/4 passed
- `tsc --noEmit`: exit 0
- 结论: **维持风险接受**；quill >2.0.3 发布后立即升级（触发条件不变）

---

## 验收快照（2026-07-31 13:0x）

- `tsc --noEmit`: exit 0 ✅
- `vitest run`: （见卡片完成证据）
- `npm run build`: （见卡片完成证据）
- `npm audit --omit=dev`: 4 vulnerabilities (2 low, 2 high) — 均为本文件记录的风险接受项，无新增
