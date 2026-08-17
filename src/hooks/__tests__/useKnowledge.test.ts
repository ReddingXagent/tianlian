/**
 * useKnowledge Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';

jest.mock('../../services/api', () => ({
  knowledgeApi: {
    getArticles: jest.fn(),
    search: jest.fn(),
  },
}));

import { useKnowledge } from '../useKnowledge';
import { knowledgeApi } from '../../services/api';

const mockGetArticles = knowledgeApi.getArticles as jest.MockedFunction<typeof knowledgeApi.getArticles>;
const mockSearch = knowledgeApi.search as jest.MockedFunction<typeof knowledgeApi.search>;

const MOCK_ITEMS = [
  { id: 1, title: 'T1', summary: 'S1', content: 'C1', tags: ['a'], author: 'Au1', viewCount: 5, createdAt: '2024-01-01', updatedAt: '2024-01-02' },
  { id: 2, title: 'T2', summary: 'S2', content: 'C2', tags: ['b'], author: 'Au2', viewCount: 10, createdAt: '2024-01-03', updatedAt: '2024-01-04' },
];

describe('useKnowledge', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetArticles.mockResolvedValue({ data: { items: MOCK_ITEMS } } as never);
    mockSearch.mockResolvedValue({ data: { items: [MOCK_ITEMS[0]] } } as never);
  });

  it('初始挂载加载文章列表', async () => {
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.articles.length).toBe(2);
    expect(result.current.articles[0].title).toBe('T1');
    expect(result.current.error).toBeNull();
  });

  it('加载失败设置error', async () => {
    mockGetArticles.mockRejectedValueOnce(new Error('500') as never);
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('加载知识库失败，请下拉刷新重试');
  });

  it('fetchArticles(isRefresh=true) 设置refreshing', async () => {
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.loading).toBe(false));
    mockGetArticles.mockClear();
    await act(async () => { await result.current.fetchArticles(true); });
    expect(result.current.refreshing).toBe(false);
    expect(mockGetArticles).toHaveBeenCalled();
  });

  it('有searchQuery时调用search而非getArticles', async () => {
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.loading).toBe(false));
    mockSearch.mockClear();
    mockGetArticles.mockClear();
    await act(async () => {
      result.current.setSearchQuery('keyword');
    });
    await waitFor(() => expect(mockSearch).toHaveBeenCalledWith('keyword'));
  });

  it('setActiveCategory 清空searchQuery', async () => {
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => {
      result.current.setSearchQuery('kw');
    });
    act(() => result.current.setActiveCategory('faq'));
    expect(result.current.searchQuery).toBe('');
    expect(result.current.activeCategory).toBe('faq');
  });

  it('mapItem: category默认other, authorId默认0', async () => {
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.articles.length).toBe(2));
    expect(result.current.articles[0].category).toBe('other');
    expect(result.current.articles[0].authorId).toBe(0);
    expect(result.current.articles[0].authorName).toBe('Au1');
  });
});
