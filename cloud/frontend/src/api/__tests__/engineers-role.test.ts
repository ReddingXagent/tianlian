/**
 * userAPI.engineers 回归测试 (卡 c51ae9bd)
 *
 * 背景: 后端 commit 57380d119 将 GET /users 的 role Query 收紧为小写 Literal
 *   ('viewer'/'operator'/'engineer'/'admin'), 前端曾发送大写 'ENGINEER' → 422,
 *   工单转派弹窗(TransferModal)加载不到工程师列表。
 *
 * 锁定行为: engineers() 发送的 role 参数必须是小写 'engineer'。
 */
import { describe, it, expect, beforeEach } from 'vitest';
import api, { userAPI } from '../index';

beforeEach(() => {
  api.defaults.adapter = (async () => ({ data: { code: 200, data: [] }, status: 200, statusText: 'OK', headers: {}, config: {} })) as any;
});

describe('userAPI.engineers (卡 c51ae9bd)', () => {
  it("role 参数发送小写 'engineer', 匹配后端 Literal", async () => {
    const calls: any[] = [];
    api.defaults.adapter = (async (config: any) => {
      calls.push(config);
      return { data: { code: 200, data: [] }, status: 200, statusText: 'OK', headers: {}, config };
    }) as any;

    await userAPI.engineers();

    expect(calls).toHaveLength(1);
    expect(calls[0].params).toEqual({ role: 'engineer' });
    expect(calls[0].params.role).toBe('engineer');
  });
});
