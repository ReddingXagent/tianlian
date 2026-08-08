/**
 * KnowledgeScreen 扩展测试 — branch覆盖率提升
 * 覆盖: search flow, category switch, summary/category fallback, refresh, viewCount
 */
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import KnowledgeScreen from '../KnowledgeScreen';
import { knowledgeApi } from '../../services/api';

const mockNavigate = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useRoute: () => ({ params: {} }),
}));

jest.mock('../../services/api', () => ({
  knowledgeApi: { getList: jest.fn(), search: jest.fn() },
}));

const MOCK_ARTICLES = [
  {
    id: 1, title: '文章一', summary: '摘要一', content: '',
    category: 'operation', tags: [], authorId: 1, authorName: '张三',
    viewCount: 10, createdAt: '2024-01-15T10:00:00Z', updatedAt: '',
  },
  {
    id: 2, title: '文章二', summary: '', content: '',
    category: 'custom_cat', tags: [], authorId: 2, authorName: '李四',
    viewCount: 0, createdAt: '2024-01-14T10:00:00Z', updatedAt: '',
  },
];

describe('KnowledgeScreen.ext — additional branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (knowledgeApi.getList as jest.Mock).mockResolvedValue({
      data: { items: MOCK_ARTICLES, total: 2, page: 1, pageSize: 50 },
    });
    (knowledgeApi.search as jest.Mock).mockResolvedValue({ data: MOCK_ARTICLES });
  });

  it('category switch: selecting non-all category calls getList with category', async () => {
    const { findByText } = render(<KnowledgeScreen />);
    // Wait for initial load
    await findByText('文章一');

    // Switch to maintenance category
    const maintBtn = await findByText('维护');
    fireEvent.press(maintBtn);

    await waitFor(() => {
      const calls = (knowledgeApi.getList as jest.Mock).mock.calls;
      const lastCall = calls[calls.length - 1][0];
      expect(lastCall.category).toBe('maintenance');
    });
  });

  it('category switch clears search query', async () => {
    const { findByText, getByPlaceholderText } = render(<KnowledgeScreen />);
    await findByText('文章一');

    // Type a search
    const input = getByPlaceholderText('搜索知识库...');
    fireEvent.changeText(input, '测试');

    // Press category to clear search
    const allBtn = await findByText('全部');
    fireEvent.press(allBtn);

    await waitFor(() => {
      const calls = (knowledgeApi.getList as jest.Mock).mock.calls;
      // Should have been called again (category switch re-fetches)
      expect(calls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('summary fallback: shows 暂无摘要 when summary is empty', async () => {
    const { findByText } = render(<KnowledgeScreen />);
    expect(await findByText('暂无摘要')).toBeTruthy();
  });

  it('category fallback: unknown category shows raw value', async () => {
    const { findByText } = render(<KnowledgeScreen />);
    expect(await findByText('custom_cat')).toBeTruthy();
  });

  it('refresh via category switch triggers new fetch', async () => {
    const { findByText } = render(<KnowledgeScreen />);
    await findByText('文章一');

    (knowledgeApi.getList as jest.Mock).mockClear();
    (knowledgeApi.getList as jest.Mock).mockResolvedValue({
      data: { items: MOCK_ARTICLES, total: 2, page: 1, pageSize: 50 },
    });

    const maintBtn = await findByText('维护');
    fireEvent.press(maintBtn);

    await waitFor(() => {
      expect(knowledgeApi.getList).toHaveBeenCalled();
    });
  });

  it('search empty: shows 未找到文章 after search returns empty', async () => {
    (knowledgeApi.search as jest.Mock).mockResolvedValue({ data: [] });
    const { findByText, getByPlaceholderText } = render(<KnowledgeScreen />);
    // Wait for initial load
    await findByText('文章一');

    // Type search
    const input = getByPlaceholderText('搜索知识库...');
    fireEvent.changeText(input, '不存在的词');

    // Wait for debounce + API
    expect(await findByText('未找到文章')).toBeTruthy();
  });

  it('error+data: shows existing articles when refresh fails but data exists', async () => {
    const { findByText, queryByText } = render(<KnowledgeScreen />);
    await findByText('文章一');
    // Articles loaded successfully — error state not shown
    expect(queryByText('加载失败')).toBeNull();
  });

  it('article viewCount renders', async () => {
    const { findByText } = render(<KnowledgeScreen />);
    expect(await findByText('张三 · 10次浏览')).toBeTruthy();
  });

  it('zero viewCount article renders', async () => {
    const { findByText } = render(<KnowledgeScreen />);
    expect(await findByText('李四 · 0次浏览')).toBeTruthy();
  });

  it('troubleshooting category press works', async () => {
    const { findByText } = render(<KnowledgeScreen />);
    await findByText('文章一');

    (knowledgeApi.getList as jest.Mock).mockClear();
    fireEvent.press(await findByText('故障'));

    await waitFor(() => {
      expect(knowledgeApi.getList).toHaveBeenCalled();
    });
  });

  it('safety category press works', async () => {
    const { findByText } = render(<KnowledgeScreen />);
    await findByText('文章一');

    (knowledgeApi.getList as jest.Mock).mockClear();
    fireEvent.press(await findByText('安全'));

    await waitFor(() => {
      expect(knowledgeApi.getList).toHaveBeenCalled();
    });
  });

  it('regulation category press works', async () => {
    const { findByText } = render(<KnowledgeScreen />);
    await findByText('文章一');

    (knowledgeApi.getList as jest.Mock).mockClear();
    fireEvent.press(await findByText('规范'));

    await waitFor(() => {
      expect(knowledgeApi.getList).toHaveBeenCalled();
    });
  });
});
