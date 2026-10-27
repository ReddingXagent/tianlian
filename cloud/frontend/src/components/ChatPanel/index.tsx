/**
 * 天链助手 - AI对话浮窗组件
 *
 * 功能:
 * - 右下角浮动按钮，点击展开对话面板
 * - 文字输入 + 语音输入 (Web Speech API)
 * - TTS播报回答
 * - 上下文感知: 自动收集当前页面数据
 * - RAG增强: 后端自动匹配知识库
 */
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Input, Button, Tag, Tooltip, Typography, Alert } from 'antd';
import {
  MessageOutlined,
  CloseOutlined,
  SendOutlined,
  SoundOutlined,
  StopOutlined,
  AudioOutlined,
  LoadingOutlined,
  DeleteOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { useLocation } from 'react-router-dom';
import {
  sendChatMessage,
  startSTT,
  speakText,
  stopSpeaking,
  voiceManager,
  type ChatMessage,
} from '../../services/chat';
import { collectPageContext, describeContext, type PageContext } from '../../services/contextInjection';
import { subscribeAuthChange } from '../../utils/authEvents';

const { Text, Paragraph } = Typography;

// 欢迎语: 账户切换清空对话历史时, 重置为这条全新会话开场白
const INITIAL_MESSAGES: ChatMessage[] = [
  {
    role: 'assistant',
    content:
      '👋 你好！我是**天链助手**，可以帮你：\n\n🔧 回答运维问题\n📊 查询设备数据\n📖 查找知识文档\n💡 提供操作指导\n\n请问有什么可以帮你的？',
  },
];

// ==================== 样式 ====================

const styles: Record<string, React.CSSProperties> = {
  fab: {
    position: 'fixed',
    bottom: 24,
    right: 24,
    width: 56,
    height: 56,
    borderRadius: '50%',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    boxShadow: '0 4px 16px rgba(102,126,234,0.4)',
    zIndex: 1300,
    border: 'none',
    transition: 'all 0.3s ease',
  },
  panel: {
    position: 'fixed',
    bottom: 90,
    right: 24,
    width: 400,
    maxHeight: 600,
    background: '#fff',
    borderRadius: 16,
    boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
    zIndex: 1300,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    transition: 'all 0.3s ease',
  },
  header: {
    padding: '16px 20px',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    cursor: 'pointer',
  },
  messages: {
    flex: 1,
    overflowY: 'auto',
    padding: '16px',
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    background: '#f8f9fc',
  },
  userBubble: {
    alignSelf: 'flex-end',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: '#fff',
    padding: '10px 16px',
    borderRadius: '16px 16px 4px 16px',
    maxWidth: '80%',
    fontSize: 14,
    lineHeight: 1.5,
    wordBreak: 'break-word',
  },
  assistantBubble: {
    alignSelf: 'flex-start',
    background: '#fff',
    color: '#333',
    padding: '10px 16px',
    borderRadius: '16px 16px 16px 4px',
    maxWidth: '80%',
    fontSize: 14,
    lineHeight: 1.5,
    boxShadow: '0 1px 4px rgba(0,0,0,0.05)',
    wordBreak: 'break-word',
  },
  inputArea: {
    padding: '12px 16px',
    borderTop: '1px solid #f0f0f0',
    display: 'flex',
    gap: 8,
    alignItems: 'flex-end',
    background: '#fff',
  },
  sourceTag: {
    fontSize: 11,
    padding: '0 4px',
    lineHeight: '16px',
  },
};

// ==================== 组件 ====================

const ChatPanel: React.FC = () => {
  const [visible, setVisible] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [showSource, setShowSource] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<any>(null);
  const location = useLocation();

  // 自动滚动到最新消息
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 聚焦输入框
  useEffect(() => {
    if (visible) {
      setTimeout(() => inputRef.current?.focus(), 300);
    }
  }, [visible]);

  // 页面上下文（缓存，页面切换时刷新）
  const [pageContext, setPageContext] = useState<PageContext | null>(null);

  // 监听路由变化，自动刷新上下文
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const ctx = await collectPageContext();
      if (!cancelled) {
        setPageContext(ctx);
      }
    })();
    return () => { cancelled = true; };
  }, [location]);

  // 账户切换(登出/换号) → 清空对话历史与上下文缓存, 杜绝跨账户串话
  useEffect(() => {
    return subscribeAuthChange(() => {
      setMessages(INITIAL_MESSAGES);
      setPageContext(null);
    });
  }, []);

  // 收集页面上下文（异步，包含API数据）
  const getPageContext = useCallback(async (): Promise<Record<string, unknown>> => {
    return collectPageContext();
  }, [location]);

  // 发送消息
  const handleSend = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || loading) return;

    setInputValue('');
    const userMsg: ChatMessage = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const context = await getPageContext();
      // history: 除去第一条欢迎消息之外的对话历史
      const history = messages.slice(1).map((m) => ({ role: m.role, content: m.content } as ChatMessage));
      const result = await sendChatMessage(text, history, context);
      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: result.answer,
      };
      setMessages((prev) => [...prev, assistantMsg]);

      // 如果有来源，附带显示
      if (result.sources && result.sources.length > 0) {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          last.content += `\n\n📚 *参考: ${result.sources.join(', ')}*`;
          return [...prev];
        });
      }
    } catch (e: any) {
      const errorMsg: ChatMessage = {
        role: 'assistant',
        content: `❌ 对话出错: ${e?.message || '未知错误'}\n\n请检查网络连接后重试。`,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  }, [inputValue, loading, messages, getPageContext]);

  // 语音输入
  const handleVoiceInput = useCallback(async () => {
    if (recording) return;
    setRecording(true);

    try {
      const text = await startSTT();
      if (text) {
        setInputValue(text);
        // 自动发送
        setTimeout(() => {
          setInputValue('');
          setMessages((prev) => [...prev, { role: 'user', content: text }]);
          setLoading(true);

          (async () => {
            try {
              const context = await getPageContext();
              const history = messages.slice(1).map((m) => ({ role: m.role, content: m.content } as ChatMessage));
              const result = await sendChatMessage(text, history, context);
              setMessages((prev) => [...prev, { role: 'assistant', content: result.answer }]);
              // 自动语音播报
              if (voiceManager.getTTSProvider().isAvailable()) {
                setSpeaking(true);
                await speakText(result.answer);
                setSpeaking(false);
              }
            } catch (e: any) {
              setMessages((prev) => [...prev, { role: 'assistant', content: `❌ ${e?.message || '对话出错'}` }]);
            } finally {
              setLoading(false);
            }
          })();
        }, 100);
      }
    } catch (e: any) {
      console.warn('语音输入失败:', e);
    } finally {
      setRecording(false);
    }
  }, [recording, messages, getPageContext]);

  // TTS播报回答
  const handleSpeak = useCallback(
    async (content: string) => {
      if (speaking) {
        stopSpeaking();
        setSpeaking(false);
        return;
      }
      setSpeaking(true);
      try {
        await speakText(content);
      } catch (e) {
        console.warn('TTS失败:', e);
      } finally {
        setSpeaking(false);
      }
    },
    [speaking]
  );

  // 清空对话
  const handleClear = useCallback(() => {
    setMessages([
      {
        role: 'assistant',
        content: '👋 对话已清空，请问有什么可以帮你的？',
      },
    ]);
  }, []);

  // 键盘事件
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  // 登录页不显示助手浮窗 (App 无条件挂载 ChatPanel, 由内部按路由屏蔽)
  if (location.pathname === '/login') return null;

  return (
    <>
      {/* 悬浮按钮 */}
      <button
        style={styles.fab}
        onClick={() => setVisible(!visible)}
        title="天链助手"
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLElement).style.transform = 'scale(1.1)';
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLElement).style.transform = 'scale(1)';
        }}
      >
        {visible ? <CloseOutlined style={{ fontSize: 20 }} /> : <RobotOutlined style={{ fontSize: 22 }} />}
      </button>

      {/* 对话面板 */}
      {visible && (
        <div style={styles.panel}>
          {/* 头部 */}
          <div style={styles.header}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <RobotOutlined style={{ fontSize: 18 }} />
              <strong>天链助手</strong>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button
                type="text"
                size="small"
                icon={<DeleteOutlined />}
                onClick={handleClear}
                style={{ color: 'rgba(255,255,255,0.8)' }}
                title="清空对话"
              />
              <Button
                type="text"
                size="small"
                icon={<CloseOutlined />}
                onClick={() => setVisible(false)}
                style={{ color: '#fff' }}
                title="关闭"
              />
            </div>
          </div>

          {/* 消息列表 */}
          <div style={styles.messages}>
            {messages.map((msg, idx) => (
              <div key={idx}>
                <div style={msg.role === 'user' ? styles.userBubble : styles.assistantBubble}>
                  <div style={{ whiteSpace: 'pre-wrap' }}>
                    {msg.role === 'assistant' ? renderMarkdown(msg.content) : msg.content}
                  </div>
                </div>
                {/* 助手消息的操作按钮 */}
                {msg.role === 'assistant' && idx > 0 && (
                  <div
                    style={{
                      display: 'flex',
                      gap: 4,
                      marginTop: 4,
                      marginLeft: 8,
                      alignItems: 'center',
                    }}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={speaking ? <StopOutlined /> : <SoundOutlined />}
                      onClick={() => handleSpeak(msg.content)}
                      style={{ fontSize: 12, color: '#999' }}
                      title={speaking ? '停止播报' : '语音播报'}
                    />
                  </div>
                )}
              </div>
            ))}

            {/* 加载指示器 */}
            {loading && (
              <div style={{ ...styles.assistantBubble, display: 'flex', alignItems: 'center', gap: 8 }}>
                <LoadingOutlined style={{ color: '#667eea' }} />
                <span style={{ color: '#999', fontSize: 13 }}>思考中...</span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* 输入区域 */}
          <div style={styles.inputArea}>
            <Input.TextArea
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入运维问题..."
              autoSize={{ minRows: 1, maxRows: 4 }}
              style={{
                flex: 1,
                border: 'none',
                borderRadius: 8,
                resize: 'none',
                fontSize: 14,
                background: '#f5f5f5',
                padding: '8px 12px',
              }}
              disabled={loading}
            />
            <Button
              type="primary"
              icon={recording ? <LoadingOutlined /> : <AudioOutlined />}
              onClick={handleVoiceInput}
              disabled={loading}
              style={{
                borderRadius: '50%',
                width: 36,
                height: 36,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: recording
                  ? '#ff4d4f'
                  : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                border: 'none',
                flexShrink: 0,
              }}
              title={recording ? '录音中...' : '语音输入'}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSend}
              disabled={!inputValue.trim() || loading}
              style={{
                borderRadius: '50%',
                width: 36,
                height: 36,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                border: 'none',
                flexShrink: 0,
              }}
              title="发送"
            />
          </div>

          {/* 底部提示 */}
          <div
            style={{
              padding: '6px 16px',
              fontSize: 11,
              color: '#bbb',
              textAlign: 'center',
              background: '#fafafa',
              borderTop: '1px solid #f0f0f0',
            }}
          >
            AI回答仅供参考，关键操作请确认后执行 · 按 Enter 发送
          </div>
        </div>
      )}
    </>
  );
};

// ==================== Markdown 简单渲染 ====================

function renderMarkdown(text: string): React.ReactNode {
  if (!text) return null;

  // 简单的Markdown渲染（换行、粗体、列表、代码块）
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeContent = '';
  let codeLang = '';

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith('```')) {
      if (inCodeBlock) {
        elements.push(
          <pre
            key={`code-${i}`}
            style={{
              background: '#f0f2f5',
              padding: 12,
              borderRadius: 8,
              fontSize: 12,
              overflowX: 'auto',
              fontFamily: 'monospace',
            }}
          >
            <code>{codeContent.trim()}</code>
          </pre>
        );
        codeContent = '';
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
        codeLang = line.slice(3).trim();
      }
      continue;
    }

    if (inCodeBlock) {
      codeContent += line + '\n';
      continue;
    }

    // 空行
    if (!line.trim()) {
      elements.push(<br key={`br-${i}`} />);
      continue;
    }

    // 普通文本：处理粗体、链接
    let content: React.ReactNode = line;

    // 粗体 **text**
    content = line.split(/(\*\*[^*]+\*\*)/g).map((part, j) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={j}>{part.slice(2, -2)}</strong>;
      }
      return part;
    });

    // 列表项
    if (line.match(/^[-*]\s/)) {
      elements.push(
        <div key={`li-${i}`} style={{ display: 'flex', gap: 6, paddingLeft: 8 }}>
          <span>•</span>
          <span>{content}</span>
        </div>
      );
      continue;
    }

    // 数字列表项
    if (line.match(/^\d+\.\s/)) {
      elements.push(
        <div key={`li-${i}`} style={{ display: 'flex', gap: 6, paddingLeft: 8 }}>
          <span>{line.match(/^\d+\./)?.[0]}</span>
          <span>{content}</span>
        </div>
      );
      continue;
    }

    // 标题（# 开头）
    if (line.startsWith('### ')) {
      elements.push(
        <div key={`h3-${i}`} style={{ fontSize: 15, fontWeight: 600, marginTop: 4, marginBottom: 2 }}>
          {line.slice(4)}
        </div>
      );
      continue;
    }
    if (line.startsWith('## ')) {
      elements.push(
        <div key={`h2-${i}`} style={{ fontSize: 16, fontWeight: 600, marginTop: 6, marginBottom: 2 }}>
          {line.slice(3)}
        </div>
      );
      continue;
    }
    if (line.startsWith('# ')) {
      elements.push(
        <div key={`h1-${i}`} style={{ fontSize: 17, fontWeight: 700, marginTop: 6, marginBottom: 2 }}>
          {line.slice(2)}
        </div>
      );
      continue;
    }

    elements.push(<div key={`p-${i}`}>{content}</div>);
  }

  return <div>{elements}</div>;
}

export default ChatPanel;