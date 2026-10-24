/**
 * 确定性兜底工具单元测试
 * 验收：纯函数、无 Math.random、相同输入恒等输出
 */
import { describe, it, expect } from 'vitest';
import {
  deterministicSeries,
  deterministicValue,
  buildTimeAxis,
  clampFinite,
} from '../deterministic';

describe('deterministicSeries', () => {
  it('相同入参恒等输出（确定性，非随机）', () => {
    expect(deterministicSeries(35, 5, 2)).toEqual(deterministicSeries(35, 5, 2));
  });

  it('长度与精度正确', () => {
    const out = deterministicSeries(10, 3, 1);
    expect(out).toHaveLength(3);
    out.forEach(v => expect(v).toBeLessThanOrEqual(11.05));
    out.forEach(v => expect(v).toBeGreaterThanOrEqual(8.95));
  });

  it('不含 NaN/Infinity', () => {
    deterministicSeries(0, 10, 5).forEach(v => expect(Number.isFinite(v)).toBe(true));
  });
});

describe('deterministicValue', () => {
  it('给定相同 (base, t) 恒等输出', () => {
    expect(deterministicValue(220, 1000, 3)).toBe(deterministicValue(220, 1000, 3));
  });

  it('输出在 [base-amp, base+amp] 区间', () => {
    for (let t = 0; t < 100; t++) {
      const v = deterministicValue(50, t, 5);
      expect(v).toBeGreaterThanOrEqual(44.9);
      expect(v).toBeLessThanOrEqual(55.1);
    }
  });
});

describe('buildTimeAxis', () => {
  it('返回等间隔递增时间戳，长度 == points', () => {
    const axis = buildTimeAxis(5, 1000, 10000);
    expect(axis).toHaveLength(5);
    expect(axis[4] > axis[0]).toBe(true);
  });
});

describe('clampFinite', () => {
  it('非法值降级为兜底默认值', () => {
    expect(clampFinite(NaN, 1)).toBe(1);
    expect(clampFinite(Infinity, 1)).toBe(1);
    expect(clampFinite(null as any, 7)).toBe(7);
    expect(clampFinite(undefined as any, 7)).toBe(7);
  });
  it('合法值原样返回', () => {
    expect(clampFinite(42, 1)).toBe(42);
  });
});
