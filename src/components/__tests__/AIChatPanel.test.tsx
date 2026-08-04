import React from 'react';
import { render, fireEvent, waitFor } from '@testing-library/react-native';
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
});
