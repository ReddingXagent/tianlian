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

  // --- F1477: cover L58, L65-66, L72, L112 ---

  it('fetchArticles(false) 调用getArticles并setLoading(true)路径', async () => {
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.loading).toBe(false));
    mockGetArticles.mockClear();
    await act(async () => { await result.current.fetchArticles(false); });
    expect(mockGetArticles).toHaveBeenCalledWith({ page: 1, page_size: 50 });
    expect(result.current.loading).toBe(false);
  });

  it('fetchArticles catch设置error (L72)', async () => {
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.loading).toBe(false));
    mockGetArticles.mockRejectedValueOnce(new Error('500') as never);
    await act(async () => { await result.current.fetchArticles(false); });
    expect(result.current.error).toBe('加载知识库失败，请下拉刷新重试');
    expect(result.current.loading).toBe(false);
  });

  it('fetchArticles(isRefresh=true) with searchQuery调用search路径 (L65-66)', async () => {
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.loading).toBe(false));
    // Set search query first, then refresh
    await act(async () => {
      result.current.setSearchQuery('battery');
    });
    await waitFor(() => expect(mockSearch).toHaveBeenCalled());
    mockSearch.mockClear();
    await act(async () => { await result.current.fetchArticles(true); });
    expect(mockSearch).toHaveBeenCalledWith('battery');
    expect(result.current.refreshing).toBe(false);
  });

  it('setSearchQuery debounce triggers fetchArticles (L112)', async () => {
    jest.useFakeTimers();
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.loading).toBe(false));
    mockGetArticles.mockClear();
    mockSearch.mockClear();
    act(() => {
      result.current.setSearchQuery('solar');
    });
    // Fast-forward debounce timer
    await act(async () => { jest.advanceTimersByTime(500); });
    await waitFor(() => expect(mockSearch).toHaveBeenCalledWith('solar'));
    jest.useRealTimers();
  });

  it('mapSearchResult: nullish author/updatedAt fallback (L27-30)', async () => {
    mockSearch.mockResolvedValueOnce({
      data: { items: [{ id: 99, title: 'T', summary: 'S', author: null, updatedAt: null }] },
    } as never);
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.loading).toBe(false));
    // Trigger search
    await act(async () => {
      result.current.setSearchQuery('nulltest');
    });
    await waitFor(() => expect(result.current.articles.length).toBeGreaterThan(0));
    const article = result.current.articles.find(a => a.id === 99);
    expect(article).toBeDefined();
    expect(article!.authorName).toBe('');
    expect(article!.updatedAt).toBe('');
  });

  it('setSearchQuery二次调用清除已有timeout (L110 true分支)', async () => {
    jest.useFakeTimers();
    const { result } = renderHook(() => useKnowledge());
    await waitFor(() => expect(result.current.loading).toBe(false));
    mockSearch.mockClear();
    // First call sets timeout ref
    act(() => { result.current.setSearchQuery('first'); });
    // Second call should clear existing timeout (L110 true branch) then set new
    act(() => { result.current.setSearchQuery('second'); });
    await act(async () => { jest.advanceTimersByTime(600); });
    // Both debounce and useEffect may trigger search; just verify no crash and 'second' was called
    expect(mockSearch.mock.calls.some((c: unknown[]) => c[0] === 'second')).toBe(true);
    jest.useRealTimers();
  });
});
