/**
 * diagnosis.ts / scan.ts 共享 axios 实例 — 回归测试
 *
 * 背景: 这两个文件曾各自 axios.create() 独立实例, 绕过 src/api/index.ts 的
 *   - 请求拦截器 (Authorization Bearer token + X-Team-Id 团队隔离)
 *   - 响应拦截器 ({code,data,message} 解套 + 401 跳登录)
 * 此测试断言它们的方法调用经共享实例, 拦截器生效, 防止回退到独立实例。
 *
 * 原理: 用假 adapter 替换共享 api.defaults.adapter 捕获最终请求 config。
 * 若被测方法改回独立 axios.create(), 请求不经共享实例, captured 为 null → 断言失败。
 */
import { describe, it, expect, beforeEach } from 'vitest';
import api from '../index';
import { diagnosisAPI } from '../diagnosis';
import { scanAPI } from '../scan';

beforeEach(() => {
  localStorage.clear();
});

/**
 * 触发一次被测调用, 捕获其经共享 api 实例的最终请求 config (拦截器已应用)。
 * 不真正发出网络请求。返回 null 表示该调用未经过共享 api 实例 (即绕过了拦截器)。
 */
async function captureSharedRequest(
  trigger: () => Promise<unknown>,
): Promise<{ url: unknown; headers: Record<string, unknown> } | null> {
  let captured: any = null;
  const origAdapter = api.defaults.adapter;
  api.defaults.adapter = async (config: any) => {
    if (captured === null) captured = config; // 只捕获第一次请求
    // 后端统一响应包装 {code,data,message}; code:200 时响应拦截器自动解套 → response.data = {}
    // (code 必须 200: 业务码校验上线后, code≠200 会被拦截器当业务错误 reject)
    return {
      data: { code: 200, data: {}, message: 'ok' },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    };
  };
  try {
    await trigger();
  } finally {
    api.defaults.adapter = origAdapter;
  }
  if (!captured) return null;
  const h: any = captured.headers;
  const get = (key: string) => (typeof h.get === 'function' ? h.get(key) : h[key]);
  return {
    url: captured.url,
    headers: {
      'X-Team-Id': get('X-Team-Id'),
      Authorization: get('Authorization'),
    },
  };
}

describe('diagnosis.ts — 共享 axios 实例 (拦截器不绕过)', () => {
  it('diagnoseDevice 经共享实例, 请求带 X-Team-Id (团队隔离)', async () => {
    const captured = await captureSharedRequest(() => diagnosisAPI.diagnoseDevice(1));
    expect(captured, 'diagnoseDevice 未经过共享 api 实例 → 拦截器被绕过').not.toBeNull();
    expect(captured!.url).toBe('/diagnosis/device');
    expect(captured!.headers['X-Team-Id']).toBe('0'); // 平台默认
  });

  it('diagnoseBatch 经共享实例, 请求带 X-Team-Id', async () => {
    const captured = await captureSharedRequest(() => diagnosisAPI.diagnoseBatch({}));
    expect(captured, 'diagnoseBatch 未经过共享 api 实例 → 拦截器被绕过').not.toBeNull();
    expect(captured!.url).toBe('/diagnosis/batch');
    expect(captured!.headers['X-Team-Id']).toBe('0');
  });

  it('getHealthTrend 经共享实例, 请求带 Authorization Bearer token', async () => {
    localStorage.setItem('admin_token', 'test-token-abc');
    const captured = await captureSharedRequest(() => diagnosisAPI.getHealthTrend(1, 30));
    expect(captured, 'getHealthTrend 未经过共享 api 实例 → 拦截器被绕过').not.toBeNull();
    expect(captured!.url).toBe('/diagnosis/health-trend/1');
    expect(captured!.headers['Authorization']).toBe('Bearer test-token-abc');
  });

  it('getStationSummary 经共享实例, 请求带 X-Team-Id', async () => {
    const captured = await captureSharedRequest(() => diagnosisAPI.getStationSummary(1));
    expect(captured, 'getStationSummary 未经过共享 api 实例 → 拦截器被绕过').not.toBeNull();
    expect(captured!.url).toBe('/diagnosis/station-summary/1');
    expect(captured!.headers['X-Team-Id']).toBe('0');
  });
});

describe('scan.ts — 共享 axios 实例 (拦截器不绕过)', () => {
  it('scanDevice 经共享实例, 请求带 X-Team-Id (团队隔离)', async () => {
    const captured = await captureSharedRequest(() => scanAPI.scanDevice('TL-DEV001'));
    expect(captured, 'scanDevice 未经过共享 api 实例 → 拦截器被绕过').not.toBeNull();
    expect(captured!.url).toBe('/scan/device');
    expect(captured!.headers['X-Team-Id']).toBe('0');
  });

  it('quickRepair 经共享实例, 请求带 X-Team-Id', async () => {
    const captured = await captureSharedRequest(() =>
      scanAPI.quickRepair({ device_id: 1, fault_desc: '故障' }),
    );
    expect(captured, 'quickRepair 未经过共享 api 实例 → 拦截器被绕过').not.toBeNull();
    expect(captured!.url).toBe('/scan/quick-repair');
    expect(captured!.headers['X-Team-Id']).toBe('0');
  });

  it('generateQRCode 经共享实例, 请求带 Authorization (有 token 时)', async () => {
    localStorage.setItem('admin_token', 'qr-token');
    const captured = await captureSharedRequest(() =>
      scanAPI.generateQRCode({ device_id: 1 }),
    );
    expect(captured, 'generateQRCode 未经过共享 api 实例 → 拦截器被绕过').not.toBeNull();
    expect(captured!.url).toBe('/scan/qrcode/generate');
    expect(captured!.headers['Authorization']).toBe('Bearer qr-token');
  });
});
