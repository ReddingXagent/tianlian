/**
 * KnowledgeDetailScreen coverage test — targets error || '文章不存在' branch
 * F1450: KnowledgeDetailScreen.tsx branches 92.85%→100%
 */
import React from 'react';
import { render } from '@testing-library/react-native';

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { articleId: 1 } }),
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../hooks/useKnowledgeDetail', () => ({
  useKnowledgeDetail: jest.fn(),
}));

import { useKnowledgeDetail } from '../../hooks/useKnowledgeDetail';
import KnowledgeDetailScreen from '../KnowledgeDetailScreen';

const mockHook = useKnowledgeDetail as jest.MockedFunction<typeof useKnowledgeDetail>;

describe('KnowledgeDetailScreen — falsy error fallback branch', () => {
  it('shows "文章不存在" when error is null but article is missing', () => {
    mockHook.mockReturnValue({
      articleId: '999',
      article: null,
      loading: false,
      error: null,
      fetchDetail: jest.fn(),
    });

    const { getByText } = render(<KnowledgeDetailScreen />);
    expect(getByText('文章不存在')).toBeTruthy();
  });

  it('shows custom error message when error is non-empty string', () => {
    mockHook.mockReturnValue({
      articleId: '1',
      article: null,
      loading: false,
      error: '网络异常请重试',
      fetchDetail: jest.fn(),
    });

    const { getByText } = render(<KnowledgeDetailScreen />);
    expect(getByText('网络异常请重试')).toBeTruthy();
  });

  it('shows "文章不存在" when error is empty string', () => {
    mockHook.mockReturnValue({
      articleId: '1',
      article: null,
      loading: false,
      error: '',
      fetchDetail: jest.fn(),
    });

    const { getByText } = render(<KnowledgeDetailScreen />);
    expect(getByText('文章不存在')).toBeTruthy();
  });
});
