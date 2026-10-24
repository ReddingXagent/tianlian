/**
 * 天链V3 - Vitest Setup 配置
 *
 * 提供:
 * - jest-dom 扩展
 * - 全局 Mock (ResizeObserver, matchMedia, localStorage)
 * - MSW 初始化
 */
import '@testing-library/jest-dom';
import { configure } from '@testing-library/react';
import { vi } from 'vitest';

// ============ testing-library 异步超时调优 ============
// waitFor / findBy 默认 1000ms timeout —— 在 vitest forks 并行 (maxForks:2) 下，
// antd 表格/Form + jsdom 渲染被并发 CPU 竞争拖慢，企业名回填/表格数据常膨胀到 2~3s，
// 默认 1s 误判超时 → 全量并行跑 flaky (单独跑同文件 400~600ms 全绿)。
// 提到 5000ms 留足并行膨胀余量；成功用例条件满足即返回，不拖慢通过用例。
// 根治 Fleet settings 等 getByXxx 查企业名并行 flaky。
configure({ asyncUtilTimeout: 5000 });

// ============ 全局 Mock ============

// ResizeObserver Mock (antd Charts 需要)
global.ResizeObserver = class ResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
} as any;

// window.matchMedia Mock
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// localStorage Mock
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    }),
    get length() {
      return Object.keys(store).length;
    },
    key: vi.fn((index: number) => Object.keys(store)[index] || null),
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
});

// sessionStorage Mock
Object.defineProperty(window, 'sessionStorage', {
  value: localStorageMock,
});

// ============ console Mock (可选) ============
// 避免测试输出过多日志
// vi.spyOn(console, 'log').mockImplementation(() => {});
// vi.spyOn(console, 'warn').mockImplementation(() => {});
// vi.spyOn(console, 'error').mockImplementation(() => {});

// ============ 每个测试前清理 ============
beforeEach(() => {
  localStorageMock.clear();
  vi.clearAllMocks();
});

// ============ 每个测试后恢复 ============
afterEach(() => {
  vi.restoreAllMocks();
});