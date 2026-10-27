/**
 * 天链V3 - 测试工具函数
 *
 * 提供:
 * - renderWithProviders: 带路由/状态管理的渲染
 * - mockAPI: API Mock 工具
 * - waitFor: 异步等待工具
 * - createMockRouter: Mock 路由
 */
import React from 'react';
import { render, RenderOptions, RenderResult } from '@testing-library/react';
import { BrowserRouter, MemoryRouter, Routes, Route } from 'react-router-dom';
import { vi } from 'vitest';

// ============ 类型定义 ============
type ProviderProps = {
  router?: boolean;
  initialRoute?: string;
  routes?: Array<{ path: string; element: React.ReactNode }>;
};

// ============ renderWithProviders ============
/**
 * 带 Providers 的渲染函数
 * 
 * @example
 * // 基础渲染 (无路由)
 * renderWithProviders(<Button>Click</Button>)
 * 
 * @example
 * // 带路由渲染
 * renderWithProviders(<LoginPage />, { router: true, initialRoute: '/login' })
 */
export function renderWithProviders(
  ui: React.ReactElement,
  options?: Omit<RenderOptions, 'wrapper'> & ProviderProps
): RenderResult {
  const { router = false, initialRoute = '/', routes, ...renderOptions } = options || {};

  const Wrapper = ({ children }: { children: React.ReactNode }) => {
    if (!router) {
      return children;
    }

    if (routes) {
      return (
        <MemoryRouter initialEntries={[initialRoute]}>
          <Routes>
            {routes.map((r) => (
              <Route key={r.path} path={r.path} element={r.element} />
            ))}
            <Route path="*" element={children} />
          </Routes>
        </MemoryRouter>
      );
    }

    return <MemoryRouter initialEntries={[initialRoute]}>{children}</MemoryRouter>;
  };

  return render(ui, { wrapper: Wrapper, ...renderOptions });
}

// ============ createMockRouter ============
/**
 * 创建 Mock Router Hook
 */
export function createMockRouter(initialPath = '/') {
  return {
    pathname: initialPath,
    navigate: vi.fn(),
    push: vi.fn(),
    replace: vi.fn(),
    go: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  };
}

// ============ mockAPI ============
/**
 * 创建 API Mock
 * 
 * @example
 * const mockGetStations = mockAPI('get', '/api/stations', { data: [...] })
 */
export function mockAPI(method: 'get' | 'post' | 'put' | 'delete' | 'patch', url: string, response: any) {
  return vi.fn().mockResolvedValue({
    data: response,
    status: 200,
    statusText: 'OK',
  });
}

/**
 * 创建 API Error Mock
 */
export function mockAPIError(method: string, url: string, error: { status: number; message: string }) {
  return vi.fn().mockRejectedValue({
    response: {
      status: error.status,
      data: { message: error.message },
    },
  });
}

// ============ mockAxios ============
/**
 * Mock Axios 实例
 */
export function mockAxiosInstance() {
  return {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  };
}

// ============ mockLocalStorage ============
/**
 * Mock localStorage with test data
 */
export function mockAuthStorage(token?: string, user?: object) {
  const testToken = token || 'test-token-12345';
  const testUser = user || { username: 'testuser', role: 'admin' };

  localStorage.setItem('admin_token', testToken);
  localStorage.setItem('admin_user', JSON.stringify(testUser));

  return { token: testToken, user: testUser };
}

/**
 * 清除 auth storage
 */
export function clearAuthStorage() {
  localStorage.removeItem('admin_token');
  localStorage.removeItem('admin_user');
}

// ============ waitForCondition ============
/**
 * 等待条件满足
 */
export async function waitForCondition(
  condition: () => boolean,
  timeout = 5000,
  interval = 100
): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (condition()) return true;
    await new Promise((resolve) => setTimeout(resolve, interval));
  }
  return false;
}

// ============ flushPromises ============
/**
 * 等待所有 Promise 完成
 */
export function flushPromises(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

// ============ createMockProps ============
/**
 * 创建 Mock Props 工具
 */
export function createMockProps<T>(defaults: T, overrides?: Partial<T>): T {
  return { ...defaults, ...overrides } as T;
}