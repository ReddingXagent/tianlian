# 前端测试覆盖率提升方案

## 背景
天链V3系统后端测试充足（340个测试文件），但前端测试几乎空白（仅3个测试文件）。为提高代码质量和可靠性，需要系统性提升前端测试覆盖率。

## 现状分析

### 后端测试 ✅
- 总测试文件: 340个
- 单元测试: 完善
- API测试: 模拟器测试套件
- 覆盖率: 估计>80%

### 前端测试 ❌
- 总测试文件: 3个 (均为依赖库的测试文件)
- 自有组件测试: 0个
- 页面测试: 0个
- E2E测试: 0个
- 覆盖率: 接近0%

### 风险
1. 回归错误难以发现
2. 重构风险高
3. 代码质量无保障
4. 发布信心不足

## 目标

### 短期目标 (v1.1发布前)
1. ✅ 核心组件单元测试覆盖 > 60%
2. ✅ 关键页面功能测试
3. ✅ 基本E2E测试流程 (登录→首页→工单)

### 中期目标 (v1.2)
1. ✅ 组件单元测试覆盖 > 80%
2. ✅ 页面集成测试全覆盖
3. ✅ E2E测试核心业务流程

### 长期目标 (v2.0)
1. ✅ 测试驱动开发文化
2. ✅ 自动化测试流水线
3. ✅ 测试覆盖率持续监控

## 技术选型

### 单元测试
- **框架**: Vitest (Vite原生支持)
- **断言**: Vitest内置
- **DOM测试**: Testing Library
- **API模拟**: MSW (Mock Service Worker)

### E2E测试
- **框架**: Playwright (多浏览器支持)
- **录制工具**: Playwright Codegen
- **断言**: Playwright内置
- **并行执行**: Playwright Workers

### 集成测试
- **组合**: Vitest + Testing Library
- **路由测试**: Memory Router
- **状态管理**: Redux/MobX测试工具

## 实施计划

### Phase 1: 测试基础设施搭建 (1天)
1. 安装测试依赖
2. 配置测试脚本
3. 创建基础测试工具
4. 设置测试环境变量

### Phase 2: 核心组件测试 (2天)
1. **优先级1组件** (15个)
   - Button, Input, Select, Table, Modal
   - 表单验证组件
   - 数据展示组件

2. **优先级2组件** (20个)
   - 图表组件 (ECharts)
   - 富文本编辑器
   - 文件上传组件
   - 日期选择器

### Phase 3: 页面功能测试 (3天)
1. **关键页面** (10个)
   - 登录/注册页
   - Dashboard首页
   - 工单管理页
   - 设备管理页
   - 告警中心页
   - 知识库页
   - 报表分析页
   - 用户管理页
   - 站点管理页
   - 系统配置页

### Phase 4: E2E测试 (2天)
1. **核心业务流程** (5个)
   - 用户登录→登出
   - 工单创建→派单→处理→验收
   - 设备添加→监控→告警
   - 知识库创建→编辑→分享
   - 报表生成→导出

### Phase 5: 持续集成 (1天)
1. GitHub Actions配置
2. 自动化测试流水线
3. 覆盖率报告
4. 测试结果通知

## 测试优先级矩阵

| 类别 | 组件/页面 | 优先级 | 测试类型 | 预计工时 |
|------|-----------|--------|----------|----------|
| **认证** | 登录/注册 | P0 | 单元+E2E | 4h |
| **核心业务** | 工单管理 | P0 | 单元+集成+E2E | 8h |
| **核心业务** | 设备管理 | P0 | 单元+集成 | 6h |
| **核心业务** | 告警中心 | P0 | 单元+集成 | 6h |
| **数据展示** | Dashboard | P1 | 单元+集成 | 6h |
| **内容管理** | 知识库 | P1 | 单元+集成 | 4h |
| **数据分析** | 报表分析 | P1 | 单元 | 4h |
| **系统管理** | 用户管理 | P2 | 单元 | 3h |
| **系统管理** | 站点管理 | P2 | 单元 | 3h |
| **系统管理** | 配置管理 | P2 | 单元 | 2h |
| **通用组件** | Form组件 | P0 | 单元 | 6h |
| **通用组件** | Table组件 | P0 | 单元 | 4h |
| **通用组件** | Modal组件 | P1 | 单元 | 2h |
| **通用组件** | Chart组件 | P1 | 单元 | 4h |

**总预计工时**: 68小时 ≈ 8.5人天

## 依赖安装清单

### package.json 新增依赖
```json
{
  "devDependencies": {
    "vitest": "^1.0.0",
    "@testing-library/react": "^15.0.0",
    "@testing-library/jest-dom": "^6.0.0",
    "@testing-library/user-event": "^14.0.0",
    "msw": "^2.0.0",
    "@playwright/test": "^1.40.0",
    "@vitest/ui": "^1.0.0",
    "jsdom": "^23.0.0",
    "@vitejs/plugin-react": "^4.0.0",
    "@types/react": "^18.0.0",
    "@types/react-dom": "^18.0.0"
  }
}
```

## 测试目录结构

```
frontend/
├── src/
│   ├── components/
│   │   ├── Button/
│   │   │   ├── Button.tsx
│   │   │   ├── Button.test.tsx      # 单元测试
│   │   │   └── index.ts
│   │   └── ...
│   ├── pages/
│   │   ├── Login/
│   │   │   ├── index.tsx
│   │   │   ├── Login.test.tsx       # 页面测试
│   │   │   └── index.css
│   │   └── ...
│   ├── hooks/
│   │   ├── useWebSocket.ts
│   │   └── useWebSocket.test.ts     # Hook测试
│   └── utils/
│       ├── format.ts
│       └── format.test.ts           # 工具函数测试
├── tests/
│   ├── e2e/
│   │   ├── login.spec.ts            # E2E测试
│   │   ├── workorder.spec.ts
│   │   └── ...
│   ├── fixtures/
│   │   └── test-data.json           # 测试数据
│   └── setup/
│       └── test-setup.ts            # 测试配置
├── vitest.config.ts                 # Vitest配置
├── playwright.config.ts             # Playwright配置
└── ...
```

## 测试配置示例

### Vitest配置 (vitest.config.ts)
```typescript
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup/test-setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'dist/',
        '**/*.d.ts',
        '**/*.config.*',
        '**/*.test.*',
        '**/*.spec.*'
      ],
      thresholds: {
        lines: 60,
        functions: 60,
        branches: 50,
        statements: 60
      }
    }
  }
});
```

### Playwright配置 (playwright.config.ts)
```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 12'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
});
```

## 质量门禁

### 代码合并要求
1. ✅ 新组件必须有单元测试
2. ✅ 新页面必须有功能测试
3. ✅ 关键功能必须有E2E测试
4. ✅ 测试覆盖率不低于阈值

### CI/CD流水线
```yaml
name: Frontend Tests
on: [push, pull_request]
jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: npm ci
      - run: npm run test:unit
      - run: npm run test:coverage
  
  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: npm ci
      - run: npx playwright install --with-deps
      - run: npm run test:e2e
  
  coverage-report:
    needs: unit-tests
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: npm ci
      - run: npm run test:coverage
      - uses: codecov/codecov-action@v3
```

## 成功标准

### Phase 1 完成标志
1. ✅ 测试基础设施搭建完成
2. ✅ 核心组件测试覆盖率 > 60%
3. ✅ 至少3个E2E测试流程
4. ✅ CI/CD流水线集成

### 项目完成标志
1. ✅ 前端测试覆盖率 > 80%
2. ✅ 所有关键页面有功能测试
3. ✅ 核心业务流程有E2E测试
4. ✅ 测试流水线自动化运行
5. ✅ 团队接受测试驱动开发

## 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 学习曲线陡峭 | 中 | 中 | 提供培训文档和示例 |
| 测试编写耗时 | 高 | 高 | 优先关键路径，逐步推进 |
| 测试维护成本 | 中 | 中 | 设计可维护的测试用例 |
| 环境配置复杂 | 低 | 低 | 提供详细配置文档 |
| 团队抵触 | 低 | 中 | 展示测试价值，小步推进 |

## 下一步行动

1. [ ] 创建测试基础设施任务派给石猴
2. [ ] 制定组件测试优先级列表
3. [ ] 安排测试编写计划
4. [ ] 建立代码评审中的测试检查点

---

**更新历史**:
- 2026-05-25: 创建测试提升方案文档
- 2026-05-25: 准备实施Phase 1