/**
 * 天链V3 - Vitest 配置
 *
 * 特性:
 * - jsdom 测试环境
 * - 覆盖率报告 (v8)
 * - 全局测试 API
 * - 测试超时设置
 * - 受限并发执行（防 8GB 机器 OOM SIGKILL）
 */
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    // 测试环境
    environment: 'jsdom',

    // 并发与内存控制 —— 8GB 物理内存机器必须显式限制 fork 数。
    // 否则 vitest 默认按 CPU 核数（8 核）开 worker，每个 worker 都要加载
    // 完整 React + antd + echarts + jsdom 模块图，8 并发瞬间吃满内存被系统 SIGKILL。
    // forks pool：进程级隔离，单个 fork 崩溃不影响主进程，内存占用可预测。
    // 并发与内存控制 —— 8GB 物理内存机器必须显式限制 fork 数。
    // vitest 4.x 起移除 poolOptions，maxForks/minForks/isolate 均为顶层选项
    // (旧 poolOptions 配置会被忽略并打印 DEPRECATED 警告 → 此前 maxForks:2 实际未生效，
    // 全量跑按 CPU 核数开 fork → OOM SIGKILL 风险)。
    // forks pool：进程级隔离，单个 fork 崩溃不影响主进程，内存占用可预测。
    pool: 'forks',
    maxForks: 2, // 最多 2 fork 并发，每进程预算约 2.5GB，8GB 机器留足余量防 SIGKILL
    minForks: 1, // 至少 1 个，避免空闲时频繁回收/重建 fork
    isolate: true, // 每测试文件独立模块图 + jsdom，杜绝文件间状态泄漏

    // 全局测试 API (describe, it, expect 等)
    globals: true,
    
    // Setup 文件
    setupFiles: ['./tests/setup/vitest-setup.ts'],
    
    // 测试匹配模式
    include: ['tests/unit/**/*.{test,spec}.{ts,tsx}', 'src/**/__tests__/**/*.{test,spec}.{ts,tsx}'],
    
    // 排除 E2E 测试和现有的 Jest 测试
    exclude: ['node_modules', 'dist', 'e2e/**', 'tests/e2e/**', 'src/__tests__/**'],
    
    // 覆盖率配置
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      reportsDirectory: './coverage',
      
      // 包含/排除规则
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'node_modules/',
        'dist/',
        '**/*.d.ts',
        '**/*.config.*',
        '**/*.test.*',
        '**/*.spec.*',
        'src/main.tsx',
        'src/vite-env.d.ts',
        'src/setupTests.ts',
        'src/**/__tests__/**',
      ],
      
      // 覆盖率阈值 (Phase 1 目标)
      thresholds: {
        lines: 30,
        functions: 18,
        branches: 18,
        statements: 30,
      },
    },
    
    // 超时设置
    testTimeout: 30000,
    hookTimeout: 15000,
    teardownTimeout: 30000, // 内存压力下 worker teardown 可能变慢，放宽避免误判失败
    
    // 监听模式排除
    watchExclude: ['**/node_modules/**', '**/dist/**', '**/coverage/**'],
    
    // 报告器
    reporters: ['default'],
  },
  
  // 路径别名
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      // react-i18next 未安装（详见 tests/setup/stubs/react-i18next.ts）。
      // vitest 无法对未安装模块注册 vi.mock（注册时仍 resolve 真实路径 → 失败），
      // 必须用 alias 指向真实存在的桩文件让 resolve 成功。仅影响测试，不影响 vite build。
      'react-i18next': path.resolve(__dirname, './tests/setup/stubs/react-i18next.ts'),
    },
  },
  
  // 定义环境变量
  define: {
    'process.env.NODE_ENV': '"test"',
  },
});