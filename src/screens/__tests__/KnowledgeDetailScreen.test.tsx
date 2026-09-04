import { render, fireEvent } from '@testing-library/react-native';
import KnowledgeDetailScreen from '../KnowledgeDetailScreen';
import { knowledgeApi } from '../../services/api';

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { articleId: 1 } }),
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../services/api', () => ({
  knowledgeApi: { getArticles: jest.fn() },
}));

const MOCK_API_ITEM = {
  id: 1,
  title: '充电桩故障排查指南',
  summary: '常见故障排查',
  content: '详细正文内容',
  categoryId: 0,
  tags: ['充电桩', '故障'],
  author: '张三',
  viewCount: 128,
  status: 'published' as const,
  createdAt: '2024-01-15T10:00:00Z',
  updatedAt: '2024-01-15T10:00:00Z',
};

const MOCK_RESPONSE = {
  data: { items: [MOCK_API_ITEM], total: 1, page: 1, pageSize: 100 },
};

describe('KnowledgeDetailScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows loading spinner initially', () => {
    (knowledgeApi.getArticles as jest.Mock).mockImplementation(
      () => new Promise(() => {})
    );
    const { getByText } = render(<KnowledgeDetailScreen />);
    expect(getByText('加载文章详情...')).toBeTruthy();
  });

  it('renders article detail after loading', async () => {
    (knowledgeApi.getArticles as jest.Mock).mockResolvedValue(MOCK_RESPONSE);
    const { findByText } = render(<KnowledgeDetailScreen />);
    expect(await findByText('充电桩故障排查指南')).toBeTruthy();
    expect(await findByText('张三')).toBeTruthy();
    expect(await findByText('128次浏览')).toBeTruthy();
    expect(await findByText('充电桩')).toBeTruthy();
    expect(await findByText('详细正文内容')).toBeTruthy();
  });

  it('renders summary block when present', async () => {
    (knowledgeApi.getArticles as jest.Mock).mockResolvedValue(MOCK_RESPONSE);
    const { findByText } = render(<KnowledgeDetailScreen />);
    expect(await findByText('📝 摘要')).toBeTruthy();
    expect(await findByText('常见故障排查')).toBeTruthy();
  });

  it('shows error state when load fails', async () => {
    (knowledgeApi.getArticles as jest.Mock).mockRejectedValue(new Error('fail'));
    const { findByText } = render(<KnowledgeDetailScreen />);
    expect(await findByText('加载失败')).toBeTruthy();
    expect(await findByText('加载文章详情失败，请重试')).toBeTruthy();
    expect(await findByText('重新加载')).toBeTruthy();
  });

  it('retries when pressing the reload button', async () => {
    (knowledgeApi.getArticles as jest.Mock)
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValue(MOCK_RESPONSE);
    const { findByText } = render(<KnowledgeDetailScreen />);
    fireEvent.press(await findByText('重新加载'));
    expect(await findByText('充电桩故障排查指南')).toBeTruthy();
    expect(knowledgeApi.getArticles).toHaveBeenCalledTimes(2);
  });

  it('exposes detail testIDs for e2e (guard against children misuse)', async () => {
    const { getByTestId, findByTestId } = render(<KnowledgeDetailScreen />);
    expect(await findByTestId('knowledge-detail-scroll')).toBeTruthy();
    expect(getByTestId('knowledge-detail-card')).toBeTruthy();
  });});
