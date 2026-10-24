# 天链V3 - 前端测试基础设施

## 完成日期: 2026-05-25

---

## 测试框架

| 类型 | 框架 | 配置文件 |
|------|------|----------|
| **单元测试** | Vitest | `vitest.config.ts` |
| **E2E测试** | Playwright | `playwright.config.ts` |
| **API Mock** | MSW | `tests/setup/msw-setup.ts` |

---

## 测试脚本

```bash
# 单元测试
npm run test:unit          # 运行所有单元测试
npm run test:watch         # 监听模式
npm run test:ui            # UI模式 (可视化)
npm run test:coverage      # 生成覆盖率报告

# E2E测试
npm run test:e2e           # 运行 E2E 测试
npm run test:e2e:ui        # UI模式
npm run test:e2e:debug     # Debug模式
npm run test:e2e:report    # 查看 HTML 报告

# 完整测试
npm run test:all           # 单元+E2E 全量测试
```

---

## 目录结构

```
frontend/
├── tests/
│   ├── setup/              # 测试配置
│   │   ├── vitest-setup.ts    # Vitest 全局配置
│   │   └── msw-setup.ts       # MSW API Mock
│   ├── fixtures/           # 测试数据
│   │   └── test-data.ts       # Mock 数据
│   ├── utils/              # 测试工具
│   │   ├── test-utils.tsx     # renderWithProviders 等
│   │   └── index.ts           # 导出索引
│   ├── unit/               # 单元测试
│   │   └── *.test.tsx
│   └ integration/          # 集成测试 (待添加)
│   └── e2e/                # E2E测试 (已存在)
├── vitest.config.ts        # Vitest配置
├── playwright.config.ts    # Playwright配置
├── .env.test               # 测试环境变量
└── coverage/               # 覆盖率报告输出
```

---

## 测试工具使用

### renderWithProviders

```tsx
import { renderWithProviders } from '@/tests/utils';

// 无路由渲染
renderWithProviders(<Button>Click</Button>);

// 带路由渲染
renderWithProviders(<LoginPage />, { 
  router: true, 
  initialRoute: '/login' 
});
```

### mockAuthStorage

```tsx
import { mockAuthStorage, clearAuthStorage } from '@/tests/utils';

beforeEach(() => {
  mockAuthStorage(); // 设置默认认证
});

afterEach(() => {
  clearAuthStorage(); // 清除认证
});
```

### MSW API Mock

```tsx
import { setupMSW, mockAPIError } from '@/tests/setup/msw-setup';

describe('API测试', () => {
  setupMSW(); // 启动 MSW Server
  
  it('应处理 API 错误', () => {
    mockAPIError('/api/stations', 500, '服务器错误');
    // ...
  });
});
```

---

## 测试数据 Fixtures

```tsx
import { 
  mockUsers, 
  mockStations, 
  mockDevices,
  mockAPIResponses 
} from '@/tests/fixtures/test-data';

// 使用 Mock 数据
const station = mockStations[0];
const loginResponse = mockAPIResponses.loginSuccess;
```

---

## 覆盖率目标 (Phase 1)

| 类型 | 阈值 |
|------|------|
| Lines | 30% |
| Functions | 30% |
| Branches | 20% |
| Statements | 30% |

---

## CI/CD 配置

GitHub Actions 配置文件: `.github/workflows/frontend-tests.yml`

包含:
- 单元测试 (Vitest)
- E2E 测试 (Playwright)
- 类型检查 (TypeScript)
- Lint 检查 (ESLint)
- 覆盖率报告

---

## 下一步

### Phase 2: 核心组件测试
1. Button, Input, Select, Table, Modal
2. 表单验证组件
3. 数据展示组件

### Phase 3: 页面功能测试
1. 登录/注册页
2. Dashboard首页
3. 工单管理页

---

## 依赖清单

```json
{
  "devDependencies": {
    "vitest": "^4.1.7",
    "@vitest/ui": "^4.1.7",
    "@vitest/coverage-v8": "^4.1.7",
    "jsdom": "^29.1.1",
    "happy-dom": "^20.9.0",
    "msw": "^2.14.6",
    "@testing-library/react": "^16.3.2",
    "@testing-library/jest-dom": "^6.9.1",
    "@testing-library/user-event": "^14.6.1",
    "@playwright/test": "^1.60.0"
  }
}
```

---

## 注意事项

1. **Jest 测试兼容**: 现有 Jest 测试保留在 `src/__tests__/`，可通过 `npm run test:jest` 运行
2. **Vitest 测试位置**: 新测试放在 `tests/unit/` 目录
3. **E2E 测试依赖**: 需要 dev server 运行 (`npm run dev`)
4. **覆盖率阈值**: 当前设置较低 (30%)，Phase 2 后将提高

---

**创建者**: 石猴 Agent
**日期**: 2026-05-25 19:31 GMT+8