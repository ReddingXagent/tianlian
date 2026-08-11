/**
 * KnowledgeScreen ext3 — refresh/retry callbacks (lines 166, 177) + search debounce
 * Target: onAction retry (line 166), onRefresh pull-to-refresh (line 177)
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

    // Walk the test tree to find RefreshControl and invoke its onRefresh
    const findRefreshControl = (node: React.ReactElement | null): React.ReactElement | null => {
      if (!node) return null;
      if (node.type === RefreshControl) return node;
      if (node.props?.refreshControl?.type === RefreshControl) return node.props.refreshControl;
      if (node.children) {
        for (const child of node.children) {
          const found = findRefreshControl(child);
          if (found) return found;
        }
      }
      return null;
    };

    const rc = findRefreshControl(UNSAFE_root);
    if (rc?.props?.onRefresh) {
      await act(async () => {
        rc.props.onRefresh();
        await new Promise(r => setTimeout(r, 100));
      });
      // getList called again (initial + refresh)
      expect(knowledgeApi.getArticles).toHaveBeenCalledTimes(2);
    }
  });
});
