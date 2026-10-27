/**
 * 团队上下文工具 — Vitest 单元测试
 *
 * 覆盖:
 *   1. getCurrentTeamId / setCurrentTeamId 的 localStorage 读写与回退逻辑
 *   2. api 请求拦截器对 X-Team-Id header 的端到端注入
 */
import { describe, it, expect, beforeEach } from 'vitest';
import api from '../../api';
import {
  getCurrentTeamId,
  setCurrentTeamId,
  TEAM_ID_STORAGE_KEY,
  PLATFORM_TEAM_ID,
} from '../team';

beforeEach(() => {
  localStorage.clear();
});

describe('getCurrentTeamId', () => {
  it('localStorage 无值时回退到平台默认 (0)', () => {
    expect(getCurrentTeamId()).toBe(PLATFORM_TEAM_ID);
    expect(getCurrentTeamId()).toBe(0);
  });

  it('读取 localStorage 中持久化的团队 ID', () => {
    localStorage.setItem(TEAM_ID_STORAGE_KEY, '7');
    expect(getCurrentTeamId()).toBe(7);
  });

  it('非数字 / 负数 / 小数等非法值回退到平台默认', () => {
    localStorage.setItem(TEAM_ID_STORAGE_KEY, 'abc');
    expect(getCurrentTeamId()).toBe(0);

    localStorage.setItem(TEAM_ID_STORAGE_KEY, '-3');
    expect(getCurrentTeamId()).toBe(0);

    localStorage.setItem(TEAM_ID_STORAGE_KEY, '2.5');
    expect(getCurrentTeamId()).toBe(0);
  });
});

describe('setCurrentTeamId', () => {
  it('将团队 ID 写入 localStorage', () => {
    setCurrentTeamId(5);
    expect(localStorage.getItem(TEAM_ID_STORAGE_KEY)).toBe('5');
  });

  it('非法值不写入', () => {
    setCurrentTeamId(-1);
    expect(localStorage.getItem(TEAM_ID_STORAGE_KEY)).toBeNull();

    // @ts-expect-error 故意传入非法类型
    setCurrentTeamId('NaN');
    expect(localStorage.getItem(TEAM_ID_STORAGE_KEY)).toBeNull();
  });
});

describe('api 请求拦截器 — X-Team-Id 注入', () => {
  it('未设置团队时, 请求自动带 X-Team-Id: 0 (平台默认)', async () => {
    const headers = await captureRequestHeaders();
    expect(headers['X-Team-Id']).toBe('0');
  });

  it('设置团队后, 请求带对应的 X-Team-Id', async () => {
    localStorage.setItem(TEAM_ID_STORAGE_KEY, '12');
    const headers = await captureRequestHeaders();
    expect(headers['X-Team-Id']).toBe('12');
  });
});

/** 触发一次 api 请求并捕获最终 header (拦截器已应用), 不真正发出网络请求。 */
async function captureRequestHeaders(): Promise<Record<string, string>> {
  let captured: unknown = null;
  const origAdapter = api.defaults.adapter;
  api.defaults.adapter = async (config: any) => {
    captured = config.headers;
    return { data: {}, status: 200, statusText: 'OK', headers: {}, config };
  };
  try {
    await api.get('/probe-team-header');
  } finally {
    api.defaults.adapter = origAdapter;
  }
  const h: any = captured ?? {};
  const get = (key: string) =>
    typeof h.get === 'function' ? h.get(key) : h[key];
  return { 'X-Team-Id': get('X-Team-Id') };
}
