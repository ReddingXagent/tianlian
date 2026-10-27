/**
 * 响应拦截器 — 业务错误码校验 回归测试 (夜班深度审计 E, 卡 f0b9e1d5)
 *
 * 背景: 后端统一契约(app/core/response.py)成功 = code:200;但 app/api/ 下 57 处端点
 *   直接 error_response(code=400/404/500), HTTP 状态码全是 200, 仅 body.code !== 200。
 *   旧响应拦截器只处理 HTTP 401, 业务错误被静默当成功 → 解包 data(常为 null)、丢失
 *   message、删除失败却显示成功。
 *
 * 锁定行为:
 *   - HTTP200 + body 含 code 且 code !== 200 → reject(Error, 带 code/response/message) + message.error
 *   - HTTP200 + code === 200 → 保持原解包逻辑(resolve 内层 data)
 *   - 无 code 字段(二进制/blob/裸数据) → 一律放行
 *   - 同 message 1 秒内去重(防并发请求刷屏)
 *   - HTTP 401 → 既有逻辑不回归(login 直接 reject; 非登录清凭证 + 跳登录)
 *
 * 原理: 用假 adapter 替换 api.defaults.adapter 返回受控 body/status, 触发真实拦截器链。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { message } from 'antd';
import api from '../index';

/**
 * 假 adapter: 替换 api.defaults.adapter, 返回指定 body + HTTP status, 触发真实拦截器链。
 * 注意: axios 的 validateStatus/settle 逻辑在内置 adapter 里; 自定义 adapter 直接返回
 * response 会被当成功 resolve。故 status>=400 须显式抛带 response 的 error,
 * 模拟真实 adapter 行为, 使其进入响应拦截器的 error 分支 (401 处理在此)。
 */
function mockAdapter(body: unknown, status = 200) {
  api.defaults.adapter = (async (config: any) => {
    if (status >= 400) {
      throw Object.assign(new Error(`Request failed with status code ${status}`), {
        config,
        response: { data: body, status, statusText: 'ERROR', headers: {}, config },
      });
    }
    return { data: body, status, statusText: 'OK', headers: {}, config };
  }) as any;
}

beforeEach(() => {
  localStorage.clear();
});

describe('响应拦截器 — 业务码校验 (HTTP200 + body.code)', () => {
  it('code:200 → resolve 且解包为内层 data', async () => {
    mockAdapter({ code: 200, data: { id: 7, name: 'foo' }, message: 'ok' });
    const res = await api.get('/any');
    expect(res.data).toEqual({ id: 7, name: 'foo' });
  });

  it('code:200 且无 data 字段 → 不解包, 原样返回 (保持旧行为)', async () => {
    mockAdapter({ code: 200, message: 'ok' });
    const res = await api.get('/any');
    expect(res.data).toEqual({ code: 200, message: 'ok' });
  });

  it('HTTP200 + code:500 → reject, error 带 code/message/response', async () => {
    const body = { code: 500, message: '内部错误', data: null };
    mockAdapter(body);
    await expect(api.get('/any')).rejects.toMatchObject({
      message: '内部错误',
      code: 500,
      response: body,
    });
  });

  it('HTTP200 + code:400 → reject 带 code 400', async () => {
    mockAdapter({ code: 400, message: '参数有误' });
    await expect(api.get('/any')).rejects.toMatchObject({ code: 400, message: '参数有误' });
  });

  it('HTTP200 + code:404 → reject 带 code 404', async () => {
    mockAdapter({ code: 404, message: '资源不存在', data: null });
    await expect(api.get('/any')).rejects.toMatchObject({ code: 404 });
  });

  it('业务错误 → antd message.error 弹后端 message', async () => {
    const spy = vi.spyOn(message, 'error').mockImplementation((() => 'key') as any);
    mockAdapter({ code: 500, message: '删除失败：存在关联工单', data: null });
    await expect(api.delete('/any/1')).rejects.toThrow();
    expect(spy).toHaveBeenCalledWith('删除失败：存在关联工单');
    spy.mockRestore();
  });

  it('缺 message → message.error 兜底 "操作失败"', async () => {
    const spy = vi.spyOn(message, 'error').mockImplementation((() => 'key') as any);
    mockAdapter({ code: 500, data: null });
    await expect(api.get('/any')).rejects.toThrow();
    expect(spy).toHaveBeenCalledWith('操作失败');
    spy.mockRestore();
  });

  it('同 message 1 秒内去重 → message.error 只弹一次 (防并发刷屏)', async () => {
    const spy = vi.spyOn(message, 'error').mockImplementation((() => 'key') as any);
    mockAdapter({ code: 500, message: '重复错误', data: null });
    await expect(api.get('/a')).rejects.toThrow();
    await expect(api.get('/b')).rejects.toThrow();
    expect(spy).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });

  it('不同 message 不去重 → 各弹一次', async () => {
    const spy = vi.spyOn(message, 'error').mockImplementation((() => 'key') as any);
    mockAdapter({ code: 500, message: '错误A', data: null });
    await expect(api.get('/a')).rejects.toThrow();
    mockAdapter({ code: 404, message: '错误B', data: null });
    await expect(api.get('/b')).rejects.toThrow();
    expect(spy).toHaveBeenCalledTimes(2);
    spy.mockRestore();
  });

  it('无 code 字段(裸数据) → 一律放行 resolve', async () => {
    mockAdapter({ items: [1, 2, 3] });
    const res = await api.get('/any');
    expect(res.data).toEqual({ items: [1, 2, 3] });
  });

  it('Blob 响应(无 code 字段) → 放行, 不解包', async () => {
    const blob = new Blob(['binary-data']);
    mockAdapter(blob);
    const res = await api.get('/any');
    expect(res.data).toBe(blob);
  });
});

describe('响应拦截器 — HTTP 401 不回归', () => {
  // 兼容 AxiosError.response.status 与 axios 1.x 顶层 error.status 两种结构
  const statusOf = (e: any) => e?.response?.status ?? e?.status;

  it('login 请求 401 → 直接 reject (不触发跳转, 保留原逻辑)', async () => {
    mockAdapter({ detail: 'bad credentials' }, 401);
    try {
      await api.post('/auth/login', { username: 'x', password: 'y' });
      throw new Error('应 reject 但 resolve 了');
    } catch (e: any) {
      if (e?.message === '应 reject 但 resolve 了') throw e;
      expect(statusOf(e)).toBe(401);
    }
  });

  it('非 login 请求 401 → reject 且清凭证 (401 分支保留)', async () => {
    // 跳转为 window.location.href 赋值 (jsdom href 属性不可重定义, 无法直接 spy);
    // 401 分支会同步清除凭证 → 作为分支被进入的可靠证据。跳转逻辑本次未改动, 不回归。
    vi.useFakeTimers();
    localStorage.setItem('admin_token', 'stale-token');

    mockAdapter({ detail: 'token expired' }, 401);
    try {
      await api.get('/protected');
      throw new Error('应 reject 但 resolve 了');
    } catch (e: any) {
      if (e?.message === '应 reject 但 resolve 了') throw e;
      expect(statusOf(e)).toBe(401);
    }
    expect(localStorage.getItem('admin_token')).toBeNull(); // 凭证已同步清除
    vi.clearAllTimers(); // 不触发跳转, 避免 jsdom 导航副作用
    vi.useRealTimers();
  });
});

describe('响应拦截器 — HTTP 403 团队越权提示 (卡 d0c431d0)', () => {
  it('HTTP 403 → message.error 权限不足 + reject', async () => {
    const spy = vi.spyOn(message, 'error').mockImplementation((() => 'key') as any);
    mockAdapter({ detail: 'forbidden' }, 403);
    await expect(api.get('/any')).rejects.toMatchObject({ response: { status: 403 } });
    expect(spy).toHaveBeenCalledWith('权限不足，无法访问该团队资源');
    spy.mockRestore();
  });

  it('HTTP 403 不清凭证 (非鉴权失败, 不跳登录)', async () => {
    localStorage.setItem('admin_token', 'keep-me');
    mockAdapter({ detail: 'forbidden' }, 403);
    await expect(api.get('/any')).rejects.toMatchObject({ response: { status: 403 } });
    expect(localStorage.getItem('admin_token')).toBe('keep-me');
  });
});
