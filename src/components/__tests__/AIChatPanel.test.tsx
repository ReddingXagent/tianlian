import React from 'react';
import { render, fireEvent, waitFor, act } from '@testing-library/react-native';
import { AIChatPanel } from '../AIChatPanel';
import type { ChatMessage } from '../../services/ai';

// 显式工厂mock: axios自动mock会撞EventEmitter undefined; 工厂内用箭头包一层延迟到调用时才读mockChat(裸引用会被import hoisting撞TDZ/undefined; 本仓jest运行时jest.hoisted缺失, 不用)
const mockChat = jest.fn();
jest.mock('../../services/ai', () => ({
  chat: (...args: unknown[]) => (mockChat as jest.Mock)(...args),
}));

// 构造一条助手消息
function assistantMsg(content: string): ChatMessage {
  return { id: `a-${content.length}`, role: 'assistant', content, timestamp: 1 };
}

describe('AIChatPanel', () => {
  beforeEach(() => {
    mockChat.mockReset();
  });

  it('渲染头部/欢迎语/快捷提问', () => {
    const { getByText } = render(<AIChatPanel />);
    expect(getByText('AI 助手')).toBeTruthy();
    expect(getByText('天链V3 智能运维')).toBeTruthy();
    expect(getByText(/我是天链V3的 AI 助手/)).toBeTruthy();
    for (const q of ['仪表盘概览', '未处理的告警', '今日营收', '待处理工单']) {
      expect(getByText(q)).toBeTruthy();
    }
  });

  it('未传onClose时不渲染关闭按钮, 传了则点击触发', () => {
    const onClose = jest.fn();
    const without = render(<AIChatPanel />);
    expect(without.queryByText('✕')).toBeNull();

    const withClose = render(<AIChatPanel onClose={onClose} />);
    fireEvent.press(withClose.getByText('✕'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('发送消息: 用户消息入列且chat返回结果替换占位', async () => {
    mockChat.mockResolvedValueOnce(assistantMsg('今日营收 128 元'));
    const { getByPlaceholderText, getByText, queryByText } = render(<AIChatPanel />);

    fireEvent.changeText(getByPlaceholderText('输入你的问题…'), '今日营收');
    fireEvent.press(getByText('↑'));

    await waitFor(() => {
      expect(getByText('今日营收 128 元')).toBeTruthy();
    });
    expect(getByText('今日营收')).toBeTruthy();
    expect(mockChat).toHaveBeenCalledTimes(1);
    // chat入参含用户消息
    const callArgs = mockChat.mock.calls[0];
    expect(callArgs[0][0]).toMatchObject({ role: 'user', content: '今日营收' });
    // 占位文案已被替换
    expect(queryByText('正在查询数据…')).toBeNull();
  });

  it('请求中: 占位消息+输入框禁用', async () => {
    let resolveChat: (m: ChatMessage) => void = () => {};
    mockChat.mockReturnValueOnce(
      new Promise<ChatMessage>((resolve) => {
        resolveChat = resolve;
      })
    );
    const { getByPlaceholderText, getByText } = render(<AIChatPanel />);

    fireEvent.changeText(getByPlaceholderText('输入你的问题…'), '查告警');
    fireEvent.press(getByText('↑'));

    await waitFor(() => {
      expect(getByText('正在查询数据…')).toBeTruthy();
    });
    // 请求中输入框不可编辑
    expect(getByPlaceholderText('输入你的问题…').props.editable).toBe(false);

    resolveChat(assistantMsg('共3条未处理告警'));
    await waitFor(() => {
      expect(getByText('共3条未处理告警')).toBeTruthy();
    });
  });

  it('请求失败: 占位消息替换为错误提示而非静默', async () => {
    mockChat.mockRejectedValueOnce(new Error('网络超时'));
    const { getByPlaceholderText, getByText } = render(<AIChatPanel />);

    fireEvent.changeText(getByPlaceholderText('输入你的问题…'), '随便问');
    fireEvent.press(getByText('↑'));

    await waitFor(() => {
      expect(getByText(/抱歉，出错了：网络超时/)).toBeTruthy();
    });
  });

  it('空输入不发送', () => {
    const { getByPlaceholderText, getByText } = render(<AIChatPanel />);
    fireEvent.changeText(getByPlaceholderText('输入你的问题…'), '   ');
    fireEvent.press(getByText('↑'));
    expect(mockChat).not.toHaveBeenCalled();
  });

  it('助手Markdown内容渲染: 标题/列表/代码块', async () => {
    const md = '# 营收汇总\n- 快充: 80元\n\n```\nSELECT 1\n```';
    mockChat.mockResolvedValueOnce(assistantMsg(md));
    const { getByPlaceholderText, getByText } = render(<AIChatPanel />);

    fireEvent.changeText(getByPlaceholderText('输入你的问题…'), '营收');
    fireEvent.press(getByText('↑'));

    await waitFor(() => {
      expect(getByText('营收汇总')).toBeTruthy();
    });
    expect(getByText('快充: 80元')).toBeTruthy();
    expect(getByText('SELECT 1')).toBeTruthy();
  });

  it('Markdown补全分支: h2/h3标题+有序列表+行内粗体/斜体/代码与前置普通文本', async () => {
    const md =
      '## 二级标题\n### 三级标题\n1. 第一步\n2. 第二步\n前文 **粗体** 中间 *斜体* 尾部 `code9` 收尾';
    mockChat.mockResolvedValueOnce(assistantMsg(md));
    const { getByPlaceholderText, getByText } = render(<AIChatPanel />);

    fireEvent.changeText(getByPlaceholderText('输入你的问题…'), '格式');
    fireEvent.press(getByText('↑'));

    await waitFor(() => {
      expect(getByText('二级标题')).toBeTruthy();
    });
    expect(getByText('三级标题')).toBeTruthy();
    expect(getByText('第一步')).toBeTruthy();
    expect(getByText('第二步')).toBeTruthy();
    // 行内标记各自独立成节点, 前置普通文本不丢
    expect(getByText('粗体')).toBeTruthy();
    expect(getByText('斜体')).toBeTruthy();
    expect(getByText('code9')).toBeTruthy();
    expect(getByText(/前文/)).toBeTruthy();
    expect(getByText(/收尾/)).toBeTruthy();
  });

  it('流式渲染: onToken逐token驱动占位消息增量更新', () => {
    let onTokenCb: ((token: string) => void) | undefined;
    mockChat.mockImplementationOnce((_msgs: unknown, onToken: (t: string) => void) => {
      onTokenCb = onToken;
      return new Promise(() => {}); // 挂起, 只验流式增量
    });
    const { getByPlaceholderText, getByText } = render(<AIChatPanel />);

    fireEvent.changeText(getByPlaceholderText('输入你的问题…'), '有多少充电站');
    fireEvent.press(getByText('↑'));
    // 占位消息先入列
    expect(getByText('正在查询数据…')).toBeTruthy();

    act(() => {
      (onTokenCb as (t: string) => void)('共有');
    });
    expect(getByText('共有')).toBeTruthy();

    act(() => {
      (onTokenCb as (t: string) => void)('12个充电站');
    });
    expect(getByText('共有12个充电站')).toBeTruthy();
  });

  it('打字指示器: 400ms步进点动画循环不崩, scroll定时器安全触发', () => {
    jest.useFakeTimers();
    try {
      mockChat.mockReturnValueOnce(new Promise(() => {}));
      const { getByPlaceholderText, getByText } = render(<AIChatPanel />);
      fireEvent.changeText(getByPlaceholderText('输入你的问题…'), '测试');
      fireEvent.press(getByText('↑'));
      // 占位消息同步入列(handleSend在await前同步执行)
      expect(getByText('正在查询数据…')).toBeTruthy();
      // 推进4个动画步进+1个scrollToBottom(100ms)定时, 覆盖interval回调与scroll回调
      act(() => {
        jest.advanceTimersByTime(1700);
      });
      expect(getByText('正在查询数据…')).toBeTruthy();
    } finally {
      jest.useRealTimers();
    }
  });

  it('快捷提问: 点击填入输入框; 仪表盘概览走focus分支; 其他chip不触发focus分支', () => {
    jest.useFakeTimers();
    try {
      const { getByText, getByPlaceholderText } = render(<AIChatPanel />);
      const input = () => getByPlaceholderText('输入你的问题…');

      // 非仪表盘概览chip: 立即填值, setTimeout内条件分支为假
      fireEvent.press(getByText('未处理的告警'));
      expect(input().props.value).toBe('未处理的告警');
      act(() => {
        jest.advanceTimersByTime(60);
      });
      expect(input().props.value).toBe('未处理的告警');

      // 仪表盘概览chip: 填值+50ms后再次setInputText并走inputRef.focus()
      fireEvent.press(getByText('仪表盘概览'));
      expect(input().props.value).toBe('仪表盘概览');
      act(() => {
        jest.advanceTimersByTime(60);
      });
      expect(input().props.value).toBe('仪表盘概览');
    } finally {
      jest.useRealTimers();
    }
  });
});
