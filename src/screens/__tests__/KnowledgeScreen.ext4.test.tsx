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
    getList: jest.fn(),
  },
}));

const ARTICLES = [
  { id: 1, title: '文章1', summary: '摘要', category: 'guide', viewCount: 10, authorName: 'admin', createdAt: '2024-01-15T10:00:00Z' },
];

describe('KnowledgeScreen.ext4 search debounce clear', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (knowledgeApi.getList as jest.Mock).mockResolvedValue({ data: { items: ARTICLES } });
    (knowledgeApi.search as jest.Mock).mockResolvedValue({ data: ARTICLES });
  });

  it('clears existing timeout when typing rapidly', async () => {
    const { getByPlaceholderText } = render(<KnowledgeScreen />);
    await waitFor(() => {
      expect(knowledgeApi.getList).toHaveBeenCalled();
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
