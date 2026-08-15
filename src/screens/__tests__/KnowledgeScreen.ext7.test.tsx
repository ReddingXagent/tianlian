/**
 * KnowledgeScreen ext7 — fetchArticles search 成功分支补覆盖 (F1213)
 * 目标行: 64 (search resolve → setArticles(mapItem))
 * 背景: F1206 ext6 只测了 onRefresh-with-search 的 reject 版(L70 catch), L64 成功路径缺口;
 *       实测 coverage 98.41% 仅缺 L64 (status 旧记 94.28% 系误读, F1211 同模式勘误)
 * 路径: 输入搜索词 → 等 effect 重跑(searchQuery deps)渲染新闭包 → onRefresh(true)
 *       此时 rc.props.onRefresh 捕获的 fetchArticles 闭包 searchQuery='充电'
 *       → search resolve 成功 → L64 setArticles(搜索结果)
 * 断言链: search 被调 ≥1 次且 resolve 版生效(搜索结果独有 title 出现 fail-fast 锚定)
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

const BASE_ITEM = { id: 1, title: '操作手册', summary: '摘要', content: '', categoryId: 1, tags: [], author: 'admin', viewCount: 10, status: 'published', createdAt: '2024-01-15T00:00:00Z', updatedAt: '' };
const SEARCH_ITEM = { ...BASE_ITEM, id: 2, title: '搜索独有结果标题' };
const BASE_MOCK = { data: { items: [BASE_ITEM], total: 1, page: 1, pageSize: 50 } };
const SEARCH_MOCK = { data: { items: [SEARCH_ITEM], total: 1, page: 1, pageSize: 50 } };
const flush = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe('KnowledgeScreen.ext7 — fetchArticles search success branch (L64)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (knowledgeApi.getArticles as jest.Mock).mockResolvedValue(BASE_MOCK);
    (knowledgeApi.search as jest.Mock).mockResolvedValue(SEARCH_MOCK);
  });

  it('onRefresh with active search resolves search API and renders search results', async () => {
    jest.setTimeout(15000);
    const { UNSAFE_root, findByText, queryByText, getByPlaceholderText } = render(
      <KnowledgeScreen />
    );
    // 初始加载走 getArticles 分支
    await findByText('操作手册');

    // 1) 输入搜索词 — effect 重跑(IIFE search 分支渲染 SEARCH_MOCK), 再 flush(800)
    //    让 500ms debounce 完成 — 注意 debounce 回调捕获的是 changeText 渲染帧的
    //    fetchArticles(''闭包) → 走 getArticles 分支恢复 BASE_MOCK(闭包时序实录,
    //    与 ext6 的 ≤2 断言互证); 必须等 debounce 走完再 refresh, 否则其 setArticles
    //    会在 refresh 之后落地覆盖搜索结果
    await act(async () => {
      fireEvent.changeText(getByPlaceholderText('搜索知识库...'), '充电');
      await flush(800);
    });
    // debounce 已完成: 此时列表回到 BASE_MOCK('操作手册'), 组件闭包 searchQuery='充电'

    // 2) 换 search mock 计数锚定: 清零后只统计本次 refresh 触发的调用
    (knowledgeApi.search as jest.Mock).mockClear();

    // 3) onRefresh(true): 新闭包 searchQuery='充电' → fetchArticles(true)
    //    → L63 search + L64 setArticles(成功)
    const all = (UNSAFE_root as unknown as {
      findAllByType?: (type: unknown) => { props?: { onRefresh?: () => void } }[];
    }).findAllByType?.(RefreshControl);
    const rc = all?.[0];
    expect(rc).toBeDefined(); // fail-fast: 找不到 RefreshControl = 假绿 (F1206 教训)
    expect(typeof rc?.props?.onRefresh).toBe('function');
    await act(async () => {
      rc?.props?.onRefresh?.();
      await flush(800);
    });

    // 4) fail-fast 锚定: refresh 触发的 search 成功后 articles 被替换 —
    //    SEARCH_ITEM 独有 title 在, BASE_ITEM 独有 title 不在(被替换)
    expect((knowledgeApi.search as jest.Mock).mock.calls.length).toBeGreaterThanOrEqual(1);
    expect(queryByText('操作手册')).toBeNull();
    await findByText('搜索独有结果标题');
  });
});
