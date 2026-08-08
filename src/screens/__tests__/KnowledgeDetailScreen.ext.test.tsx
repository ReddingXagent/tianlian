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
  knowledgeApi: { getDetail: jest.fn() },
}));

const FULL_ARTICLE = {
  id: 1,
  title: '测试文章',
  summary: '摘要内容',
  content: '正文内容',
  category: 'troubleshooting',
  tags: ['标签1', '标签2'],
  authorId: 1,
  authorName: '作者',
  viewCount: 10,
  createdAt: '2024-01-15T10:00:00Z',
  updatedAt: '2024-01-15T10:00:00Z',
};

describe('KnowledgeDetailScreen.ext — branch coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders without tags when tags array is empty', async () => {
    (knowledgeApi.getDetail as jest.Mock).mockResolvedValue({
      data: { ...FULL_ARTICLE, tags: [] },
    });
    const { findByText, queryByText } = render(<KnowledgeDetailScreen />);
    expect(await findByText('测试文章')).toBeTruthy();
    // No tag elements rendered
    expect(queryByText('标签1')).toBeNull();
  });

  it('hides summary block when summary is null', async () => {
    (knowledgeApi.getDetail as jest.Mock).mockResolvedValue({
      data: { ...FULL_ARTICLE, summary: null },
    });
    const { findByText, queryByText } = render(<KnowledgeDetailScreen />);
    expect(await findByText('测试文章')).toBeTruthy();
    expect(queryByText('📝 摘要')).toBeNull();
  });

  it('shows fallback text when content is empty', async () => {
    (knowledgeApi.getDetail as jest.Mock).mockResolvedValue({
      data: { ...FULL_ARTICLE, content: '' },
    });
    const { findByText } = render(<KnowledgeDetailScreen />);
    expect(await findByText('暂无详细内容')).toBeTruthy();
  });

  it('shows "文章不存在" when response data is null without error', async () => {
    (knowledgeApi.getDetail as jest.Mock).mockResolvedValue({ data: null });
    const { findByText } = render(<KnowledgeDetailScreen />);
    expect(await findByText('文章不存在')).toBeTruthy();
  });
});
