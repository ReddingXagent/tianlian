/**
 * KnowledgeScreen ext3 — refresh/retry callbacks + search debounce
 * F1206: 替换树遍历为 findAllByType — 旧 walk 找不到 RefreshControl(宿主组件包装 FlatList
 * 的 refreshControl prop 之外形态), `if (rc?.props?.onRefresh)` 守卫使断言静默空转,
 * onRefresh 分支(line 220)覆盖为假。findAllByType 实测能找到(F1206 探针 FINDALL_COUNT=1)。
 */
import { render, fireEvent, act } from '@testing-library/react-native';
import React from 'react';
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

const MOCK_ARTICLES = {
  data: {
    items: [
      { id: 1, title: '操作手册', summary: '摘要', content: '', categoryId: 1, tags: [], author: 'admin', viewCount: 10, status: 'published', createdAt: '2024-01-15T00:00:00Z', updatedAt: '' },
      { id: 2, title: '维护指南', summary: '', content: '', categoryId: 0, tags: [], author: 'admin', viewCount: 0, status: 'published', createdAt: '', updatedAt: '' },
    ],
    total: 2,
    page: 1,
    pageSize: 50,
  },
};

describe('KnowledgeScreen.ext3 — refresh & retry callbacks', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (knowledgeApi.getArticles as jest.Mock).mockResolvedValue(MOCK_ARTICLES);
    (knowledgeApi.search as jest.Mock).mockResolvedValue({ data: { items: [], total: 0, page: 1, pageSize: 50 } });
  });

  // Line 166: onAction retry when error & empty articles
  it('triggers fetchArticles via onAction when error with no articles', async () => {
    jest.setTimeout(15000);
    (knowledgeApi.getArticles as jest.Mock).mockRejectedValueOnce(new Error('Network error'));

    const { findByText } = render(<KnowledgeScreen />);

    // Wait for error to show
    const retryButton = await findByText('重新加载');

    // Fix mock to succeed on retry
    (knowledgeApi.getArticles as jest.Mock).mockResolvedValueOnce(MOCK_ARTICLES);

    await act(async () => {
      fireEvent.press(retryButton);
      await new Promise(r => setTimeout(r, 100));
    });

    expect(knowledgeApi.getArticles).toHaveBeenCalledTimes(2);
  });

  // Line 177: onRefresh pull-to-refresh with existing data
  it('triggers fetchArticles(true) via onRefresh when articles exist', async () => {
    jest.setTimeout(15000);
    const { UNSAFE_root, findByText } = render(<KnowledgeScreen />);

    // Wait for initial load
    await findByText('操作手册');

    // F1206: findAllByType 直接定位 RefreshControl 实例(旧树遍历在此组件形态下找不到)
    const all = (UNSAFE_root as unknown as {
      findAllByType?: (type: unknown) => { props?: { onRefresh?: () => void } }[];
    }).findAllByType?.(RefreshControl);
    const rc = all?.[0];
    // 不再用 if 守卫包裹断言 — 找不到时 fail fast, 防止假绿
    expect(rc).toBeDefined();
    expect(typeof rc?.props?.onRefresh).toBe('function');
    await act(async () => {
      rc?.props?.onRefresh?.();
      await new Promise(r => setTimeout(r, 100));
    });
    // getList called again (initial + refresh)
    expect(knowledgeApi.getArticles).toHaveBeenCalledTimes(2);
  });
});
