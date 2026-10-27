# 天链 V3 前端（Web 管理后台）

React 18 + Vite 5 + Ant Design 5 + ECharts 6 的光储充运维管理后台，含设备监控、告警工单、数字孪生（three.js）、运营结算、车队管理等模块。

---

## 环境要求

| 项 | 要求 | 说明 |
|----|------|------|
| Node.js | 18+（Vite 5 最低）；推荐 20+（Vitest 4） | 项目无 `.nvmrc` / `engines` 约束，实测 v24 可用 |
| 包管理 | npm（随 Node） | `package-lock.json` 已锁定依赖 |

主要依赖：React 18、react-router-dom 6、antd 5、echarts 6、three.js（@react-three/fiber）、axios、i18next、react-quill、xlsx。完整清单见 `package.json`。

---

## 安装

```bash
cd frontend

# 首次安装
npm install

# CI / 可重现安装（按 lock 文件）
npm ci
```

> `package.json` 的 `overrides` 强制锁定了 `brace-expansion`、`undici`、`ws` 等传递依赖版本，用于清零 dev-chain 安全漏洞，安装时属预期行为。

---

## 常用命令

| 命令 | 作用 |
|------|------|
| `npm run dev` | 启动开发服务器（端口 **3004**） |
| `npm run build` | 生产构建，输出到 `dist/` |
| `npm run preview` | 本地预览构建产物 |
| `npm run lint` | ESLint 检查 `src/**/*.{ts,tsx}` |
| `npm run format` / `format:check` | Prettier 格式化 / 校验 |
| `npm run typecheck` | `tsc --noEmit` 类型检查 |
| `npm test` / `test:unit` | Vitest 单次运行 |
| `npm run test:watch` | Vitest 监听模式 |
| `npm run test:coverage` | Vitest + coverage-v8 覆盖率 |
| `npm run test:e2e` | Playwright 端到端测试 |
| `npm run test:jest` | Jest 兼容运行（历史用例） |

---

## 开发服务器与代理配置

开发服务器监听 **3004** 端口，`vite.config.ts` 配置了 API 代理：

```ts
server: {
  port: 3004,
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
}
```

> ⚠️ **后端端口必须对齐**：proxy 固定指向 `localhost:8000`，因此本地后端必须跑在 **8000**（用项目根的 `make backend`，或 `uvicorn app.main:app --reload --port 8000`）。
> 若后端改用 `config.py` 默认的 8080，需同步把 `vite.config.ts` 的 `target` 改为 `http://localhost:8080`，否则前端 `/api/*` 请求会 502。

环境变量文件：`.env` / `.env.example` / `.env.production` / `.env.test`。

---

## 构建产物

```bash
npm run build    # 产物输出到 dist/
```

`vite.config.ts` 配置了 `manualChunks` 手动分包（vendor-antd / vendor-echarts / vendor-react / vendor-three / vendor-report / vendor-editor 等），并禁用了 sourcemap 与 PWA（管理后台不需要 Service Worker，避免缓存旧 401 导致登录闪退）。

---

## 目录结构

```
frontend/
├── src/
│   ├── main.tsx            # 应用入口
│   ├── App.tsx             # 路由配置（100+ 路由）
│   ├── pages/              # 页面（60+ 业务目录：Dashboard/Devices/Stations/
│   │                       #          Alarms/Operate/Fleet/DigitalTwin …）
│   ├── api/                # Axios API 封装（按业务域拆分）
│   ├── components/         # 通用组件
│   ├── routes/             # 路由守卫与配置
│   ├── services/           # 业务服务（含 WebSocket 客户端）
│   ├── hooks/              # 自定义 Hooks
│   ├── contexts/           # React Context（主题/权限等）
│   ├── locales/            # i18n 多语言资源
│   ├── types/              # TypeScript 类型定义
│   ├── utils/              # 工具函数
│   └── styles/             # 全局样式
├── tests/                  # 单元测试
├── e2e/                    # Playwright 端到端测试
├── vite.config.ts          # Vite + 代理 + 分包配置
├── vitest.config.ts        # Vitest 配置
├── tsconfig.json
└── package.json
```

---

## 测试

```bash
npm test              # Vitest 单次运行（主测试运行器）
npm run test:watch    # 监听模式
npm run test:coverage # 覆盖率
npm run test:e2e      # Playwright 端到端
npm run typecheck     # 类型检查（tsc --noEmit）
```

测试技术栈：Vitest 4 + @testing-library/react + happy-dom/jsdom + msw（接口 mock）+ Playwright（e2e）。

---

## 更多文档

- 后端 API：`docs/API.md` 或开发环境 `http://localhost:8000/api/docs`
- 部署流程：`docs/DEPLOY.md`
- 项目总览：项目根 `README.md`
