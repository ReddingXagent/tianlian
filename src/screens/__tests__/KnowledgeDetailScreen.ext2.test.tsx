/**
 * F1210: KnowledgeDetailScreen coverage 补测 — L45 (fetchDetail 内部 catch)
 * 源码结构: 挂载 effect 内 IIFE 自带 catch(L74) — 既有套件的错误路径都停在
 * 这一层。fetchDetail (useCallback, L21-49) 只被 EmptyState 重试按钮调用;
 * 既有 retry 测试是 挂载失败→重试成功, 从未覆盖 "重试再失败" → L45 catch。
 * 补齐链: 挂载失败(effect catch L74) → 按重试 → fetchDetail 再失败 →
 * L45 catch → setError → 空态复现 → 再按重试 → 成功恢复。
 */
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

describe('KnowledgeDetailScreen.ext2 — fetchDetail 重试链 (L45 catch)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('重试再失败: fetchDetail catch 触发 → 空态复现 (L45)', async () => {
    // 第1次: 挂载 effect 失败 → 空态
    // 第2次: 重试按钮 → fetchDetail 失败 → L45 catch
    (knowledgeApi.getArticles as jest.Mock)
      .mockRejectedValueOnce(new Error('mount fail'))
      .mockRejectedValueOnce(new Error('retry fail'));
    const { findByText, getByText } = render(<KnowledgeDetailScreen />);
    expect(await findByText('重新加载')).toBeTruthy();

    fireEvent.press(getByText('重新加载'));
    // fetchDetail 走 catch L45 → setError → 仍然空态 (非 loading 卡死)
    expect(await findByText('加载失败')).toBeTruthy();
    expect(await findByText('重新加载')).toBeTruthy();
    expect(knowledgeApi.getArticles).toHaveBeenCalledTimes(2);
  });

  it('重试失败后恢复: 第二次重试成功 → 正文渲染 (闭环)', async () => {
    (knowledgeApi.getArticles as jest.Mock)
      .mockRejectedValueOnce(new Error('mount fail'))
      .mockRejectedValueOnce(new Error('retry fail'))
      .mockResolvedValue(MOCK_RESPONSE);
    const { findByText, getByText, queryByText } = render(
      <KnowledgeDetailScreen />
    );
    expect(await findByText('重新加载')).toBeTruthy();

    // 第一次重试: 失败 (L45)
    fireEvent.press(getByText('重新加载'));
    expect(await findByText('加载失败')).toBeTruthy();

    // 第二次重试: 成功 → 正文
    fireEvent.press(getByText('重新加载'));
    expect(await findByText('充电桩故障排查指南')).toBeTruthy();
    expect(queryByText('重新加载')).toBeNull();
    expect(knowledgeApi.getArticles).toHaveBeenCalledTimes(3);
  });
});
