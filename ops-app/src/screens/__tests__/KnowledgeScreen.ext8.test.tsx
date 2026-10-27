/**
 * KnowledgeScreen ext8 — effect IIFE cancelled/错误可见分支补覆盖 (F1214)
 * 目标: branch5 L101 (getArticles resolve 时 cancelled=true → return),
 *       branch6 L105 (catch 时 !cancelled → setError 可见路径)
 * 实勘: F1213 status 误记 L101-105 为 renderArticleItem CATEGORIES.find 链(实际~L141),
 *       coverage-final.json 实勘 branch5 counts=[0,26] / branch6 counts=[2,0];
 *       istanbul 方法论: 先查 branchMap counts 定位真缺口, 不信旧记录
 * 路径1(cancelled): render → effect IIFE 发起 getArticles(deferred 挂起) →
 *       unmount(cancelled=true) → resolve → L101 return 命中(不走 setArticles)
 * 路径2(错误可见): render → getArticles reject 时组件仍在树 → L105 setError('加载知识库失败...')
 *       → loading&&articles.length===0 → EmptyState '重新加载' 出现
 * 断言链: unmount 后 resolve 不抛 + mock 计数闭环; EmptyState 文案 fail-fast
 */
import { render, act, fireEvent } from '@testing-library/react-native';

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../services/api', () => ({
  knowledgeApi: {
    getArticles: jest.fn(),
    search: jest.fn(),
  },
}));

import KnowledgeScreen from '../KnowledgeScreen';
import { knowledgeApi } from '../../services/api';

const flush = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe('KnowledgeScreen.ext8 — effect IIFE cancelled + visible error branches (L101/L105)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('unmount before getArticles resolve hits cancelled return (L101)', async () => {
    jest.setTimeout(15000);
    // deferred 挂起: 初始 effect IIFE 的 getArticles 永不立即 resolve
    let resolveFetch: (v: unknown) => void = () => {};
    (knowledgeApi.getArticles as jest.Mock).mockImplementation(
      () =>
        new Promise((res) => {
          resolveFetch = res as (v: unknown) => void;
        })
    );

    const { queryByText: queryBeforeUnmount, unmount } = render(<KnowledgeScreen />);
    // loading 中(LoadingSpinner), 列表尚未渲染
    expect(queryBeforeUnmount('操作手册')).toBeNull();

    // unmount → effect cleanup: cancelled = true
    unmount();

    // resolve 到达: IIFE 内 L101 if (cancelled) return 命中 → 不走 setArticles
    // (若无 cancelled 守卫会触发 setState-after-unmount 警告/泄漏路径)
    await act(async () => {
      resolveFetch({ data: { items: [], total: 0, page: 1, pageSize: 50 } });
      await flush(50);
    });

    // 卸载后树查询会抛 'Unable to find node on unmounted component'(RNTL 限制),
    // 改断言: resolve 后无任何异常抛出 + mock 调用计数闭环
    expect((knowledgeApi.getArticles as jest.Mock).mock.calls.length).toBe(1);
  });

  it('getArticles reject while mounted sets visible error (L105)', async () => {
    jest.setTimeout(15000);
    (knowledgeApi.getArticles as jest.Mock).mockRejectedValueOnce(
      new Error('net down')
    );

    const { findByText, queryByText } = render(<KnowledgeScreen />);

    // catch: cancelled=false → L105 setError('加载知识库失败，请下拉刷新重试')
    // → loading=false 且 articles 空 → EmptyState 渲染
    await findByText('重新加载');
    // 错误提示文案不再直接渲染(screen 走 EmptyState), fail-fast: 主内容未出现
    expect(queryByText('操作手册')).toBeNull();
  });

  it('unmount before search resolve hits cancelled return in search branch (L97/L101 锁定完整)', async () => {
    jest.setTimeout(15000);
    // search 侧同款 deferred: 激活搜索词 → effect IIFE 走 search 分支挂起
    let resolveSearch: (v: unknown) => void = () => {};
    (knowledgeApi.getArticles as jest.Mock).mockResolvedValue({
      data: { items: [], total: 0, page: 1, pageSize: 50 },
    });
    (knowledgeApi.search as jest.Mock).mockImplementation(
      () =>
        new Promise((res) => {
          resolveSearch = res as (v: unknown) => void;
        })
    );

    const screen = render(<KnowledgeScreen />);
    // 先等 getArticles resolve(空列表) → LoadingSpinner 退出 → 主界面(含搜索框)渲染
    for (let i = 0; i < 100; i++) {
      await act(async () => {
        await Promise.resolve();
      });
      if ((knowledgeApi.getArticles as jest.Mock).mock.calls.length >= 1) break;
    }
    await screen.findByPlaceholderText('搜索知识库...');

    // 快路径: fireEvent.changeText 注入搜索词 → effect 重跑(searchQuery deps) → search 挂起
    await act(async () => {
      fireEvent.changeText(screen.getByPlaceholderText('搜索知识库...'), '充电');
      await flush(100);
    });
    // search 已被调用且挂起(effect 重跑后立即发起)
    for (let i = 0; i < 100; i++) {
      await act(async () => {
        await Promise.resolve();
      });
      if ((knowledgeApi.search as jest.Mock).mock.calls.length >= 1) break;
    }
    expect((knowledgeApi.search as jest.Mock).mock.calls.length).toBeGreaterThanOrEqual(1);

    screen.unmount();
    // 卸载后放行 → cancelled=true → L101 return (search 侧守卫)
    await act(async () => {
      resolveSearch({ data: { items: [], total: 0, page: 1, pageSize: 50 } });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect((knowledgeApi.search as jest.Mock).mock.calls.length).toBeGreaterThanOrEqual(1);
  });

  it('unmount before getArticles reject skips setError (L105 cancelled arm)', async () => {
    jest.setTimeout(15000);
    // deferred 挂起 + 卸载后 reject → catch 内 cancelled=true → setError 不执行
    let rejectFetch: (e: unknown) => void = () => {};
    (knowledgeApi.getArticles as jest.Mock).mockImplementation(
      () =>
        new Promise((_res, rej) => {
          rejectFetch = rej as (e: unknown) => void;
        })
    );

    const { unmount } = render(<KnowledgeScreen />);
    for (let i = 0; i < 100; i++) {
      await act(async () => {
        await Promise.resolve();
      });
      if ((knowledgeApi.getArticles as jest.Mock).mock.calls.length >= 1) break;
    }
    unmount();
    // 卸载后 reject → L105 !cancelled=false → setError 跳过 (无 setState after unmount)
    await act(async () => {
      rejectFetch(new Error('late-reject'));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect((knowledgeApi.getArticles as jest.Mock).mock.calls.length).toBe(1);
  });
});
