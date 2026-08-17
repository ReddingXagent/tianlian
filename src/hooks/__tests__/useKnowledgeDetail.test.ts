/**
 * useKnowledgeDetail Hook 测试
 */
import { renderHook, act, waitFor } from '@testing-library/react-native';

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { articleId: 42 } }),
}));

jest.mock('../../services/api', () => ({
  knowledgeApi: {
    getArticles: jest.fn(),
  },
}));

import { useKnowledgeDetail } from '../useKnowledgeDetail';
import { knowledgeApi } from '../../services/api';

const mockGetArticles = knowledgeApi.getArticles as jest.MockedFunction<typeof knowledgeApi.getArticles>;

const MOCK_ITEMS = [
  { id: 42, title: 'Target', summary: 'S', content: 'C', tags: ['t'], author: 'Au', viewCount: 3, createdAt: '2024-01-01', updatedAt: '2024-01-02' },
  { id: 99, title: 'Other', summary: 'S2', content: 'C2', tags: ['x'], author: 'Au2', viewCount: 1, createdAt: '2024-01-03', updatedAt: '2024-01-04' },
];

describe('useKnowledgeDetail', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetArticles.mockResolvedValue({ data: { items: MOCK_ITEMS } } as never);
  });

  it('初始挂载加载文章详情', async () => {
    const { result } = renderHook(() => useKnowledgeDetail());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.article?.id).toBe(42);
    expect(result.current.article?.title).toBe('Target');
    expect(result.current.error).toBeNull();
  });

  it('articleId不匹配时设置error', async () => {
    mockGetArticles.mockResolvedValueOnce({ data: { items: [MOCK_ITEMS[1]] } } as never);
    const { result } = renderHook(() => useKnowledgeDetail());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('加载文章详情失败，请重试');
    expect(result.current.article).toBeNull();
  });

  it('API失败设置error', async () => {
    mockGetArticles.mockRejectedValueOnce(new Error('500') as never);
    const { result } = renderHook(() => useKnowledgeDetail());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('加载文章详情失败，请重试');
  });

  it('fetchDetail: 手动刷新成功', async () => {
    const { result } = renderHook(() => useKnowledgeDetail());
    await waitFor(() => expect(result.current.loading).toBe(false));
    mockGetArticles.mockClear();
    await act(async () => { await result.current.fetchDetail(); });
    expect(mockGetArticles).toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
  });

  it('articleId 从路由参数获取', () => {
    const { result } = renderHook(() => useKnowledgeDetail());
    expect(result.current.articleId).toBe(42);
  });
});
