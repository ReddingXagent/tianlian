/**
 * ChatPanel 组件测试 - 账户数据隔离
 *
 * 验证: 账户切换(登出/换号)时, 对话历史被清空, 杜绝跨账户上下文串话。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ChatPanel from '../ChatPanel';
import { sendChatMessage } from '../../services/chat';
import { broadcastAuthChange } from '../../utils/authEvents';

// jsdom 未实现 scrollIntoView, polyfill 避免 ChatPanel 自动滚动 effect 报错
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// 屏蔽对话/语音服务, 隔离 UI 行为
vi.mock('../../services/chat', () => ({
  sendChatMessage: vi.fn(),
  startSTT: vi.fn(),
  speakText: vi.fn(),
  stopSpeaking: vi.fn(),
  voiceManager: { getTTSProvider: () => ({ isAvailable: () => false }) },
}));

// 屏蔽上下文采集, 避免触发真实 API
vi.mock('../../services/contextInjection', () => ({
  collectPageContext: vi.fn().mockResolvedValue({
    page_type: 'unknown',
    url: 'http://localhost/',
    page_title: '',
  }),
  describeContext: vi.fn().mockReturnValue(''),
}));

const mockedSend = sendChatMessage as unknown as ReturnType<typeof vi.fn>;

describe('ChatPanel 账户隔离', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedSend.mockResolvedValue({
      answer: '这是助手回答',
      confidence: 0.9,
      sources: [],
      actions: [],
      needs_human: false,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderPanel = () =>
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <ChatPanel />
      </MemoryRouter>
    );

  it('账户切换后清空对话历史, 不残留上一账户内容', async () => {
    renderPanel();

    // 展开面板
    fireEvent.click(screen.getByTitle('天链助手'));

    // 初始仅欢迎语
    expect(screen.getByText(/你好！我是/)).toBeInTheDocument();

    // 输入并发送一条消息
    const textarea = screen.getByPlaceholderText('输入运维问题...') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: '上个账户的秘密数据' } });
    fireEvent.click(screen.getByTitle('发送'));

    // 用户消息 + 助手回答出现
    await waitFor(() => {
      expect(screen.getByText('上个账户的秘密数据')).toBeInTheDocument();
      expect(screen.getByText('这是助手回答')).toBeInTheDocument();
    });

    // 触发账户切换(等价于 logout / 换号广播)
    act(() => {
      broadcastAuthChange();
    });

    // 对话历史被清空: 秘密数据与助手回答都不再可见
    expect(screen.queryByText('上个账户的秘密数据')).not.toBeInTheDocument();
    expect(screen.queryByText('这是助手回答')).not.toBeInTheDocument();
  });
});
