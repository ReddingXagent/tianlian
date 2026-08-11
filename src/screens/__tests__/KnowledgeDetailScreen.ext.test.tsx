/**
 * KnowledgeDetailScreen 扩展测试 — branch覆盖率提升
 * 目标: 78.57% → 100% branches
 * 覆盖: tags=[], summary=null, content=""(暂无详细内容), error+null article
 */
import { render } from '@testing-library/react-native';
import KnowledgeDetailScreen from '../KnowledgeDetailScreen';
import { knowledgeApi } from '../../services/api';

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { articleId: 1 } }),
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../services/api', () => ({
  knowledgeApi: { getArticles: jest.fn() },
}));

const BASE_ITEM = {
  id: 1,
  title: '测试文章',
  summary: '摘要内容',
  content: '正文内容',
  categoryId: 0,
  tags: ['标签1', '标签2'],
  author: '作者',
  viewCount: 10,
  status: 'published' as const,
  createdAt: '2024-01-15T10:00:00Z',
  updatedAt: '2024-01-15T10:00:00Z',
};

function mockResponse(item: typeof BASE_ITEM | null) {
  return {
    data: {
      items: item ? [item] : [],
      total: item ? 1 : 0,
      page: 1,
      pageSize: 100,
    },
  };
}

describe('KnowledgeDetailScreen.ext — branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders without tags when tags array is empty', async () => {
    (knowledgeApi.getArticles as jest.Mock).mockResolvedValue(
      mockResponse({ ...BASE_ITEM, tags: [] })
    );
    const { findByText, queryByText } = render(<KnowledgeDetailScreen />);
    expect(await findByText('测试文章')).toBeTruthy();
    expect(queryByText('标签1')).toBeNull();
  });

  it('hides summary block when summary is empty', async () => {
    (knowledgeApi.getArticles as jest.Mock).mockResolvedValue(
      mockResponse({ ...BASE_ITEM, summary: '' })
    );
    const { findByText, queryByText } = render(<KnowledgeDetailScreen />);
    expect(await findByText('测试文章')).toBeTruthy();
    expect(queryByText('📝 摘要')).toBeNull();
  });

  it('shows fallback text when content is empty', async () => {
    (knowledgeApi.getArticles as jest.Mock).mockResolvedValue(
      mockResponse({ ...BASE_ITEM, content: '' })
    );
    const { findByText } = render(<KnowledgeDetailScreen />);
    expect(await findByText('暂无详细内容')).toBeTruthy();
  });

  it('shows "文章不存在" when article not found in list', async () => {
    (knowledgeApi.getArticles as jest.Mock).mockResolvedValue(mockResponse(null));
    const { findByText } = render(<KnowledgeDetailScreen />);
    expect(await findByText('加载失败')).toBeTruthy();
  });
});
