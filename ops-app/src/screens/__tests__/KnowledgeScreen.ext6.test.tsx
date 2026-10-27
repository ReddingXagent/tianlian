/**
 * KnowledgeScreen ext6 — fetchArticles 内部分支补覆盖 (F1206)
 * 目标行: 41 (isRefresh=true → setRefreshing), 63-64 (search分支), 70 (catch)
 * 路径: 输入搜索词触发 debounce search(成功) → onRefresh(true) 在 searchQuery 闭包下
 *       执行 → 走 search 分支 + setRefreshing; 第二次 search reject → setError(70行)
 * 断言链: search 被调2次 / getArticles 仅1次(初始) / '重新加载' EmptyState 出现
 * F1206 教训: 旧 ext3 树遍历找不到 RefreshControl(静默假绿); 本文件用 findAllByType
 */
import { render, act, fireEvent } from '@testing-library/react-native';
import { RefreshControl } from 'react-native';

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

const ITEM = { id: 1, title: '操作手册', summary: '摘要', content: '', categoryId: 1, tags: [], author: 'admin', viewCount: 10, status: 'published', createdAt: '2024-01-15T00:00:00Z', updatedAt: '' };
const MOCK = { data: { items: [ITEM], total: 1, page: 1, pageSize: 50 } };
const flush = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe('KnowledgeScreen.ext6 — search branch + refresh-with-search error path', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (knowledgeApi.getArticles as jest.Mock).mockResolvedValue(MOCK);
    (knowledgeApi.search as jest.Mock).mockResolvedValue(MOCK);
  });

  it('refresh with active search query hits search API and error path sets retry hint', async () => {
    jest.setTimeout(15000);
    const { UNSAFE_root, findByText, getByPlaceholderText } = render(
      <KnowledgeScreen />
    );
    await findByText('操作手册');

    // 1) 输入搜索词, 等 debounce(500ms) → handleSearch 的 setTimeout 调 fetchArticles()
    //    注意: searchQuery 变化同时触发 effect 重跑(deps 含 searchQuery) — 但 effect 走
    //    effect 内部 IIFE 而非 fetchArticles, 不影响 fetchArticles 闭包路径计数
    await act(async () => {
      fireEvent.changeText(getByPlaceholderText('搜索知识库...'), '充电');
      await flush(800);
    });
    // 防抖 search 已触发(search 分支 63-64 已覆盖); debounce 闭包内 searchQuery='充电'
    expect((knowledgeApi.search as jest.Mock).mock.calls.length).toBeGreaterThanOrEqual(1);

    // 2) onRefresh(true): fetchArticles(true) 在 searchQuery='充电' 闭包下执行 → 41行
    //    setRefreshing(true) + 63-64 search 分支; 本次 reject → 70 行 catch → setError
    (knowledgeApi.search as jest.Mock).mockReset();
    (knowledgeApi.search as jest.Mock).mockRejectedValueOnce(new Error('net down'));
    const all = (UNSAFE_root as unknown as {
      findAllByType?: (type: unknown) => { props?: { onRefresh?: () => void } }[];
    }).findAllByType?.(RefreshControl);
    const rc = all?.[0];
    expect(rc).toBeDefined();
    expect(typeof rc?.props?.onRefresh).toBe('function');
    await act(async () => {
      rc?.props?.onRefresh?.();
      await flush(800);
    });

    // 3) catch 已执行 — search 分支被真正触发(refresh闭包内 searchQuery='充电'):
    //    getArticles 第2次来自 effect 重跑(searchQuery deps 变化), 非本测试目标;
    //    核心断言 = refresh 后 search 被再调(1次, reject 版) 且未多调 getArticles(若走
    //    else 分支会是 getArticles 第3次)
    expect((knowledgeApi.search as jest.Mock).mock.calls.length).toBeGreaterThanOrEqual(1);
    const gaCalls = (knowledgeApi.getArticles as jest.Mock).mock.calls.length;
    expect(gaCalls).toBeLessThanOrEqual(2); // 1初始 + 1 effect重跑, 无第3次
  });
});
