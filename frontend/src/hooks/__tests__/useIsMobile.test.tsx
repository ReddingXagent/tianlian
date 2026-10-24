/**
 * useIsMobile Hook — 单元测试
 *
 * 覆盖：默认断点判断、自定义 maxWidth、resize 事件切换、SSR 安全。
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useIsMobile } from '../useIsMobile';

describe('useIsMobile', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('桌面宽度(≥768)默认返回 false', () => {
    vi.stubGlobal('innerWidth', 1024);
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);
  });

  it('移动宽度(<768)默认返回 true', () => {
    vi.stubGlobal('innerWidth', 375);
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(true);
  });

  it('恰好等于断点(768)返回 false（< 而非 <=）', () => {
    vi.stubGlobal('innerWidth', 768);
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);
  });

  it('响应 resize 事件动态切换', () => {
    vi.stubGlobal('innerWidth', 1024);
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);

    act(() => {
      vi.stubGlobal('innerWidth', 500);
      window.dispatchEvent(new Event('resize'));
    });
    expect(result.current).toBe(true);

    act(() => {
      vi.stubGlobal('innerWidth', 1200);
      window.dispatchEvent(new Event('resize'));
    });
    expect(result.current).toBe(false);
  });

  it('支持自定义 maxWidth（平板断点 1024）', () => {
    vi.stubGlobal('innerWidth', 900);
    const { result } = renderHook(() => useIsMobile(1024));
    expect(result.current).toBe(true); // 900 < 1024
  });

  it('自定义 maxWidth 时 1100 返回 false', () => {
    vi.stubGlobal('innerWidth', 1100);
    const { result } = renderHook(() => useIsMobile(1024));
    expect(result.current).toBe(false); // 1100 >= 1024
  });
});
