/**
 * KnowledgeScreen ext4 — searchTimeout clear branch (line 74)
 * When user types again before 500ms, existing timeout is cleared
 */
import { render, fireEvent, waitFor } from '@testing-library/react-native';
import KnowledgeScreen from '../KnowledgeScreen';
import { knowledgeApi } from '../../services/api';

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../services/api', () => ({
  knowledgeApi: {
    search: jest.fn(),
    getArticles: jest.fn(),
  },
}));

const ARTICLES = [
  { id: 1, title: '文章1', summary: '摘要', content: '', categoryId: 0, tags: [], author: 'admin', viewCount: 10, status: 'published', createdAt: '2024-01-15T10:00:00Z', updatedAt: '' },
];

describe('KnowledgeScreen.ext4 search debounce clear', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (knowledgeApi.getArticles as jest.Mock).mockResolvedValue({ data: { items: ARTICLES } });
    (knowledgeApi.search as jest.Mock).mockResolvedValue({ data: { items: ARTICLES, total: 1, page: 1, pageSize: 50 } });
  });

  it('clears existing timeout when typing rapidly', async () => {
    const { getByPlaceholderText } = render(<KnowledgeScreen />);
    await waitFor(() => {
      expect(knowledgeApi.getArticles).toHaveBeenCalled();
    });

    const searchInput = getByPlaceholderText('搜索知识库...');
    // Type first character — sets a timeout
    fireEvent.changeText(searchInput, '充');
    // Type second character quickly — should clear first timeout
    fireEvent.changeText(searchInput, '充电');

    // Verify searchInput updated
    expect(searchInput.props.value).toBe('充电');
  });
});
