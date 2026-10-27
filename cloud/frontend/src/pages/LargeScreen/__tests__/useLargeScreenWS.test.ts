/**
 * useLargeScreenWS Hook 测试
 * Phase48: 大屏独立展示模式 WebSocket 连接管理
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useLargeScreenWS } from '../useLargeScreenWS';
import { WS_ENDPOINTS } from '../../../config/websocket';

describe('useLargeScreenWS', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('应正确配置 WebSocket URL', () => {
    expect(WS_ENDPOINTS.largeScreen).toBeDefined();
    expect(WS_ENDPOINTS.largeScreen).toContain('/ws/v1/dashboard/large-screen');
  });

  it('应正确导出 Hook', () => {
    expect(useLargeScreenWS).toBeDefined();
    expect(typeof useLargeScreenWS).toBe('function');
  });

  it('WS_ENDPOINTS 应包含 largeScreen', () => {
    const keys = Object.keys(WS_ENDPOINTS);
    expect(keys).toContain('largeScreen');
  });
});
