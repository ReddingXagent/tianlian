import { render, fireEvent } from '@testing-library/react-native';
import KnowledgeScreen from '../KnowledgeScreen';
import { knowledgeApi } from '../../services/api';

const mockNavigate = jest.fn();

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useRoute: () => ({ params: {} }),
}));

jest.mock('../../services/api', () => ({
  knowledgeApi: { getArticles: jest.fn(), search: jest.fn() },
}));

// KnowledgeArticleItem shape (what API returns)
const MOCK_ITEMS = [
  {
    id: 1,
    title: '文章一',
    summary: '摘要一',
    content: '',
    categoryId: 1,
    tags: [],
    author: '张三',
    viewCount: 10,
    status: 'published' as const,
    createdAt: '2024-01-15T10:00:00Z',
    updatedAt: '',
  },
  {
    id: 2,
    title: '文章二',
    summary: '',
    content: '',
    categoryId: 0,
    tags: [],
    author: '李四',
    viewCount: 20,
    status: 'published' as const,
    createdAt: '2024-01-14T10:00:00Z',
    updatedAt: '',
  },
];

describe('KnowledgeScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (knowledgeApi.getArticles as jest.Mock).mockResolvedValue({
      data: { items: MOCK_ITEMS, total: 2, page: 1, pageSize: 50 },
    });
    (knowledgeApi.search as jest.Mock).mockResolvedValue({ data: { items: MOCK_ITEMS, total: 2, page: 1, pageSize: 50 } });
  });

  it('shows loading spinner initially', () => {
    (knowledgeApi.getArticles as jest.Mock).mockImplementation(
      () => new Promise(() => {})
    );
    const { getByText } = render(<KnowledgeScreen />);
    expect(getByText('加载知识库...')).toBeTruthy();
  });

  it('renders article list after loading', async () => {
    const { findByText } = render(<KnowledgeScreen />);
    expect(await findByText('文章一')).toBeTruthy();
    expect(await findByText('文章二')).toBeTruthy();
  });

  it('renders category filter chips', async () => {
    const { findByText, findAllByText } = render(<KnowledgeScreen />);
    expect(await findByText('全部')).toBeTruthy();
    expect((await findAllByText('操作')).length).toBeGreaterThanOrEqual(1);
    expect(await findByText('安全')).toBeTruthy();
  });

  it('navigates to detail when an article is pressed', async () => {
    const { findByText } = render(<KnowledgeScreen />);
    fireEvent.press(await findByText('文章一'));
    expect(mockNavigate).toHaveBeenCalledWith('KnowledgeDetail', { articleId: 1 });
  });

  it('shows empty state when no articles', async () => {
    (knowledgeApi.getArticles as jest.Mock).mockResolvedValue({
      data: { items: [], total: 0, page: 1, pageSize: 50 },
    });
    const { findByText } = render(<KnowledgeScreen />);
    expect(await findByText('暂无文章')).toBeTruthy();
  });

  it('shows error state when load fails', async () => {
    (knowledgeApi.getArticles as jest.Mock).mockRejectedValue(new Error('x'));
    const { findByText } = render(<KnowledgeScreen />);
    expect(await findByText('加载失败')).toBeTruthy();
  });

  it('exposes list/search testIDs for e2e (guard against children misuse)', async () => {
    const { getByTestId, findByTestId } = render(<KnowledgeScreen />);
    expect(await findByTestId('knowledge-card-1')).toBeTruthy();
    expect(getByTestId('knowledge-search-input')).toBeTruthy();
    expect(getByTestId('knowledge-list')).toBeTruthy();
  });});
