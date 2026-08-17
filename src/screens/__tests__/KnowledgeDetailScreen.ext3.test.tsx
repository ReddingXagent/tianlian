/**
 * KnowledgeDetailScreen.ext3 — branch coverage closure
 * 目标: 19/24 → 24/24 branches (100%)
 * 未覆盖分支:
 *   L30 block0 branch0: fetchDetail中 if(!item) throw 的 true 路径
 *   L59 block2 branch0: useEffect中 if(cancelled) return 的 true 路径
 *   L74 block3 branch1: useEffect catch中 if(!cancelled) 的 false 路径
 *   L76 block4 branch1: useEffect finally中 if(!cancelled) 的 false 路径
 *   L93 block8 branch1: error || '文章不存在' 的 false 路径 (error=null, article=null)
 *
 * 策略:
 *   - L30: 挂载成功后按重试，fetchDetail调用时返回空列表 → item不存在 → throw
 *   - L59/L74/L76: 组件挂载后延迟resolve，在resolve前unmount → cancelled=true
 *   - L93: 不可达防御代码 — error=null且article=null在正常流程中不会同时出现
 *          (useEffect中item不存在会throw→catch→setError)。通过文档化方式标注。
 */
import { render, fireEvent, act } from '@testing-library/react-native';
import KnowledgeDetailScreen from '../KnowledgeDetailScreen';
import { knowledgeApi } from '../../services/api';

jest.mock('@react-navigation/native', () => ({
  useRoute: () => ({ params: { articleId: 999 } }),
  useNavigation: () => ({ navigate: jest.fn() }),
}));

jest.mock('../../services/api', () => ({
  knowledgeApi: { getArticles: jest.fn() },
}));

const MOCK_ITEM = {
  id: 999,
  title: '测试文章',
  summary: '摘要',
  content: '正文',
  categoryId: 0,
  tags: ['标签'],
  author: '作者',
  viewCount: 5,
  status: 'published' as const,
  createdAt: '2024-01-15T10:00:00Z',
  updatedAt: '2024-01-15T10:00:00Z',
};

const MOCK_RESPONSE = {
  data: { items: [MOCK_ITEM], total: 1, page: 1, pageSize: 100 },
};

const EMPTY_RESPONSE = {
  data: { items: [], total: 0, page: 1, pageSize: 100 },
};

describe('KnowledgeDetailScreen.ext3 — branch closure', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // L30: fetchDetail中 if(!item) throw 的 true 路径
  // 挂载失败(空列表) → useEffect中item不存在→throw→catch→空态 → 按重试 → fetchDetail调用返回空列表 → item不存在 → throw → catch → 空态
  it('fetchDetail throws when article not found on retry (L30 true branch)', async () => {
    (knowledgeApi.getArticles as jest.Mock)
      .mockResolvedValue(EMPTY_RESPONSE);  // 挂载和重试都返回空列表

    const { findByText, getByText } = render(<KnowledgeDetailScreen />);
    // 挂载: useEffect调用 → 空列表 → item不存在 → throw (L58) → catch → 空态
    expect(await findByText('重新加载')).toBeTruthy();

    // 按重试按钮 → fetchDetail被调用 → 空列表 → !item → throw (L30) → catch → 空态
    fireEvent.press(getByText('重新加载'));
    // 等待fetchDetail完成（先loading再空态）
    expect(await findByText('加载失败')).toBeTruthy();
    expect(knowledgeApi.getArticles).toHaveBeenCalledTimes(2);
  });

  // L59/L74/L76: cancelled=true 路径
  // 组件挂载 → useEffect发起异步请求 → 在resolve前unmount → cancelled=true
  // → resolve后 if(cancelled) return (L59), catch中 if(!cancelled) false (L74), finally中 if(!cancelled) false (L76)
  it('cancels pending request on unmount (L59, L74, L76 cancelled branches)', async () => {
    // 创建一个可控的promise
    let resolveFn: (value: typeof MOCK_RESPONSE) => void = () => {};
    const controlledPromise = new Promise<typeof MOCK_RESPONSE>((resolve) => {
      resolveFn = resolve;
    });
    (knowledgeApi.getArticles as jest.Mock).mockReturnValue(controlledPromise);

    const { unmount, getByText } = render(<KnowledgeDetailScreen />);
    expect(getByText('加载文章详情...')).toBeTruthy();

    // 在promise resolve前卸载组件 → cleanup函数设置 cancelled=true
    unmount();

    // 现在resolve promise → useEffect中的async函数继续执行
    // → if(cancelled) return (L59 true) → 不会setArticle
    // 即使有错误也不会setError (L74 false branch), 不会setLoading (L76 false branch)
    await act(async () => {
      resolveFn(MOCK_RESPONSE);
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    // 验证组件已卸载（无错误即可）
    expect(knowledgeApi.getArticles).toHaveBeenCalledTimes(1);
  });

  // L59/L74/L76: cancelled=true 且请求失败 (覆盖L74 false branch)
  it('cancels pending request on unmount with rejection (L59, L74 cancelled catch)', async () => {
    let rejectFn: (reason: Error) => void = () => {};
    const controlledPromise = new Promise<typeof MOCK_RESPONSE>((_, reject) => {
      rejectFn = reject;
    });
    (knowledgeApi.getArticles as jest.Mock).mockReturnValue(controlledPromise);

    const { unmount, getByText } = render(<KnowledgeDetailScreen />);
    expect(getByText('加载文章详情...')).toBeTruthy();

    unmount();

    // reject后 → catch → if(!cancelled) false → 不setError
    await act(async () => {
      rejectFn(new Error('cancelled request'));
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(knowledgeApi.getArticles).toHaveBeenCalledTimes(1);
  });
});
