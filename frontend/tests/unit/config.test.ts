/**
 * Config 模块测试 - 提升覆盖率
 */
import { describe, it, expect, vi } from 'vitest';

describe('WebSocket 配置', () => {
  it('应导出 WS_BASE_URL', async () => {
    const config = await import('../../src/config/websocket');
    expect(config.WS_BASE_URL).toBeDefined();
  });

  it('应导出 WS_CONFIG', async () => {
    const config = await import('../../src/config/websocket');
    expect(config.WS_CONFIG).toBeDefined();
    expect(config.WS_CONFIG.heartbeatInterval).toBe(30);
    expect(config.WS_CONFIG.reconnectInterval).toBe(3);
    expect(config.WS_CONFIG.maxReconnectAttempts).toBe(5);
    expect(config.WS_CONFIG.connectionTimeout).toBe(10);
  });

  it('应导出 WS_ENDPOINTS', async () => {
    const config = await import('../../src/config/websocket');
    expect(config.WS_ENDPOINTS.realtime).toBeDefined();
    expect(config.WS_ENDPOINTS.dashboard).toBeDefined();
    expect(config.WS_ENDPOINTS.devices).toBeDefined();
    expect(config.WS_ENDPOINTS.alerts).toBeDefined();
    expect(config.WS_ENDPOINTS.workorders).toBeDefined();
    expect(config.WS_ENDPOINTS.digitalTwinGlobal).toBeDefined();
  });

  it('应导出 dynamic endpoints', async () => {
    const config = await import('../../src/config/websocket');
    expect(config.WS_ENDPOINTS.digitalTwinStation(1)).toContain('/1');
    expect(config.WS_ENDPOINTS.digitalTwinDevice(2)).toContain('/2');
  });

  it('应导出 WebSocketConfig default', async () => {
    const config = await import('../../src/config/websocket');
    expect(config.default).toBeDefined();
    expect(config.default.baseUrl).toBeDefined();
    expect(config.default.endpoints).toBeDefined();
    expect(config.default.config).toBeDefined();
  });
});

describe('Menu 配置', () => {
  it('应导出 getMenuItems', async () => {
    const { getMenuItems } = await import('../../src/config/menuConfig');
    expect(typeof getMenuItems).toBe('function');
    // Test with both entry types
    const platformItems = getMenuItems('platform');
    const opsItems = getMenuItems('ops');
    expect(Array.isArray(platformItems)).toBe(true);
    expect(Array.isArray(opsItems)).toBe(true);
  });

  it('应导出 getSystemTitle', async () => {
    const { getSystemTitle } = await import('../../src/config/menuConfig');
    expect(typeof getSystemTitle).toBe('function');
    const title = getSystemTitle('ops', false);
    expect(typeof title).toBe('string');
  });
});
