/**
 * lazyRetry — 懒加载 chunk 失败自动刷新自愈测试
 *
 * 场景回放：2026-10-08 /operate/points 报
 * TypeError: Failed to fetch dynamically imported module: .../index-FRuzy3rx.js
 */
import { describe, it, expect, vi, beforeEach, afterAll } from 'vitest';
import React, { Suspense } from 'react';
import { render } from '@testing-library/react';
import {
  lazyRetry,
  withChunkReload,
  isChunkLoadError,
  CHUNK_RELOAD_STORAGE_KEY,
} from '../lazyRetry';

const reloadMock = vi.fn();
const originalLocation = window.location;

beforeEach(() => {
  reloadMock.mockClear();
  sessionStorage.clear();
  // jsdom 允许 delete 后重挂 location（浏览器不行，仅测试用）
  delete window.location;
  (window as any).location = { ...originalLocation, reload: reloadMock };
});

afterAll(() => {
  (window as any).location = originalLocation;
});

const CHUNK_ERR = new TypeError(
  'Failed to fetch dynamically imported module: http://demo.example.com/assets/index-FRuzy3rx.js',
);

/** 吞掉渲染错误的最小 ErrorBoundary，避免 lazy 拒绝导致测试崩栈 */
class CatchBoundary extends React.Component<
  { children: React.ReactNode },
  { caught: boolean }
> {
  state = { caught: false };
  static getDerivedStateFromError() {
    return { caught: true };
  }
  render() {
    return this.state.caught ? <div>已捕获渲染错误</div> : this.props.children;
  }
}

describe('isChunkLoadError', () => {
  it('识别 Chrome 文案（真实案例）', () => {
    expect(isChunkLoadError(CHUNK_ERR)).toBe(true);
  });
  it('识别 Safari 文案', () => {
    expect(
      isChunkLoadError(new TypeError('Importing a module script failed: xx.js')),
    ).toBe(true);
  });
  it('识别 Firefox 文案', () => {
    expect(
      isChunkLoadError(new SyntaxError('error loading dynamically imported module: xx.js')),
    ).toBe(true);
  });
  it('非 chunk 错误不误判', () => {
    expect(isChunkLoadError(new Error('普通业务错误'))).toBe(false);
    expect(isChunkLoadError('字符串错误')).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
  });
});

describe('withChunkReload', () => {
  it('成功时原样透传，不刷新', async () => {
    await expect(withChunkReload(Promise.resolve(42))).resolves.toBe(42);
    expect(reloadMock).not.toHaveBeenCalled();
  });

  it('chunk 失败 → 整页刷新一次并重抛原错误', async () => {
    await expect(withChunkReload(Promise.reject(CHUNK_ERR))).rejects.toThrow(TypeError);
    expect(reloadMock).toHaveBeenCalledTimes(1);
  });

  it('非 chunk 失败 → 不刷新只重抛', async () => {
    await expect(withChunkReload(Promise.reject(new Error('业务错误')))).rejects.toThrow(
      '业务错误',
    );
    expect(reloadMock).not.toHaveBeenCalled();
  });

  it('冷却窗口内第二次 chunk 失败不再刷新（防死循环）', async () => {
    await expect(withChunkReload(Promise.reject(CHUNK_ERR))).rejects.toThrow();
    await expect(withChunkReload(Promise.reject(CHUNK_ERR))).rejects.toThrow();
    expect(reloadMock).toHaveBeenCalledTimes(1);
  });

  it('冷却窗口外可再次刷新', async () => {
    sessionStorage.setItem(CHUNK_RELOAD_STORAGE_KEY, String(Date.now() - 60_000));
    await expect(withChunkReload(Promise.reject(CHUNK_ERR))).rejects.toThrow();
    expect(reloadMock).toHaveBeenCalledTimes(1);
  });
});

describe('lazyRetry', () => {
  it('正常工厂 → 渲染出页面组件', async () => {
    const Page = lazyRetry(() =>
      Promise.resolve({ default: () => <div>积分管理页</div> }),
    );
    const { findByText } = render(
      <Suspense fallback={<div>loading</div>}>
        <Page />
      </Suspense>,
    );
    expect(await findByText('积分管理页')).toBeInTheDocument();
    expect(reloadMock).not.toHaveBeenCalled();
  });

  it('chunk 失败工厂 → 触发整页刷新（自愈路径）', async () => {
    const Page = lazyRetry(() => Promise.reject(CHUNK_ERR));
    render(
      <CatchBoundary>
        <Suspense fallback={<div>loading</div>}>
          <Page />
        </Suspense>
      </CatchBoundary>,
    );
    // 刷新是同步触发的，等一拍让渲染稳定
    await new Promise((r) => setTimeout(r, 0));
    expect(reloadMock).toHaveBeenCalledTimes(1);
  });
});
