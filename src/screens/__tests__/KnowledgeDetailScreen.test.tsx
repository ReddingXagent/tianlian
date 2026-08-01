import { render, fireEvent } from '@testing-library/react-native';
import KnowledgeDetailScreen from '../KnowledgeDetailScreen';
import { knowledgeApi } from '../../services/api';

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { articleId: 1 } }),
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../services/api', () => ({
  knowledgeApi: { getDetail: jest.fn() },
}));

const MOCK_ARTICLE = {
  id: 1,
  title: '充电桩故障排查指南',
  summary: '常见故障排查',
  content: '详细正文内容',
  category: 'troubleshooting',
  tags: ['充电桩', '故障'],
  authorId: 1,
  authorName: '张三',
  viewCount: 128,
  createdAt: '2024-01-15T10:00:00Z',
  updatedAt: '2024-01-15T10:00:00Z',
};

describe('KnowledgeDetailScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows loading spinner initially', () => {
    (knowledgeApi.getDetail as jest.Mock).mockImplementation(
      () => new Promise(() => {})
    );
    const { getByText } = render(<KnowledgeDetailScreen />);
    expect(getByText('加载文章详情...')).toBeTruthy();
  });

  it('renders article detail after loading', async () => {
    (knowledgeApi.getDetail as jest.Mock).mockResolvedValue({ data: MOCK_ARTICLE });
    const { findByText } = render(<KnowledgeDetailScreen />);
    expect(await findByText('充电桩故障排查指南')).toBeTruthy();
    expect(await findByText('张三')).toBeTruthy();
    expect(await findByText('128次浏览')).toBeTruthy();
    expect(await findByText('充电桩')).toBeTruthy();
    expect(await findByText('详细正文内容')).toBeTruthy();
  });

  it('renders summary block when present', async () => {
    (knowledgeApi.getDetail as jest.Mock).mockResolvedValue({ data: MOCK_ARTICLE });
    const { findByText } = render(<KnowledgeDetailScreen />);
    expect(await findByText('📝 摘要')).toBeTruthy();
    expect(await findByText('常见故障排查')).toBeTruthy();
  });

  it('shows error state when load fails', async () => {
    (knowledgeApi.getDetail as jest.Mock).mockRejectedValue(new Error('fail'));
    const { findByText } = render(<KnowledgeDetailScreen />);
    expect(await findByText('加载失败')).toBeTruthy();
    expect(await findByText('加载文章详情失败，请重试')).toBeTruthy();
    expect(await findByText('重新加载')).toBeTruthy();
  });

  it('retries when pressing the reload button', async () => {
    (knowledgeApi.getDetail as jest.Mock)
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValue({ data: MOCK_ARTICLE });
    const { findByText } = render(<KnowledgeDetailScreen />);
    fireEvent.press(await findByText('重新加载'));
    expect(await findByText('充电桩故障排查指南')).toBeTruthy();
    expect(knowledgeApi.getDetail).toHaveBeenCalledTimes(2);
  });
});
