/**
 * AI 助手聊天面板
 *
 * 提供完整的聊天界面：输入框、消息列表、打字动画、Markdown 渲染。
 * 调用 ai.ts 服务实现多轮对话和 function calling。
 *
 * @module components/AIChatPanel
 */

import React, {
  useState,
  useRef,
  useCallback,
  useEffect,
} from 'react';
import {
  View,
  Text,
  TextInput,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { chat, ChatMessage } from '../services/ai';

// =====================
// 简单 Markdown 渲染器
// =====================

/**
 * 将 Markdown 文本渲染为 React Native 组件。
 * 支持：**粗体**、*斜体*、`代码`、```代码块```、有序/无序列表、标题
 */
function renderMarkdown(text: string): React.ReactNode[] {
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeBlockLines: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]!;

    // 代码块开始/结束
    if (line.trim().startsWith('```')) {
      if (inCodeBlock) {
        // 结束代码块
        elements.push(
          <View key={`code-${i}`} style={mdStyles.codeBlock}>
            <Text style={mdStyles.codeText}>{codeBlockLines.join('\n')}</Text>
          </View>
        );
        codeBlockLines = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeBlockLines.push(line);
      continue;
    }

    // 空行
    if (line.trim() === '') {
      elements.push(<View key={`br-${i}`} style={{ height: 8 }} />);
      continue;
    }

    // 标题
    if (line.startsWith('### ')) {
      elements.push(
        <Text key={`h3-${i}`} style={mdStyles.h3}>
          {renderInlineMarkdown(line.slice(4))}
        </Text>
      );
      continue;
    }
    if (line.startsWith('## ')) {
      elements.push(
        <Text key={`h2-${i}`} style={mdStyles.h2}>
          {renderInlineMarkdown(line.slice(3))}
        </Text>
      );
      continue;
    }
    if (line.startsWith('# ')) {
      elements.push(
        <Text key={`h1-${i}`} style={mdStyles.h1}>
          {renderInlineMarkdown(line.slice(2))}
        </Text>
      );
      continue;
    }

    // 无序列表
    if (line.match(/^[\-\*]\s/)) {
      elements.push(
        <View key={`li-${i}`} style={mdStyles.listItem}>
          <Text style={mdStyles.bullet}>•</Text>
          <Text style={mdStyles.listText}>
            {renderInlineMarkdown(line.replace(/^[\-\*]\s/, ''))}
          </Text>
        </View>
      );
      continue;
    }

    // 有序列表
    const olMatch = line.match(/^(\d+)\.\s/);
    if (olMatch && olMatch[1]) {
      elements.push(
        <View key={`ol-${i}`} style={mdStyles.listItem}>
          <Text style={mdStyles.bullet}>{olMatch[1]}.</Text>
          <Text style={mdStyles.listText}>
            {renderInlineMarkdown(line.replace(/^\d+\.\s/, ''))}
          </Text>
        </View>
      );
      continue;
    }

    // 普通段落
    elements.push(
      <Text key={`p-${i}`} style={mdStyles.paragraph}>
        {renderInlineMarkdown(line)}
      </Text>
    );
  }

  return elements;
}

/**
 * 行内 Markdown 渲染：**粗体**、*斜体*、`行内代码`
 */
function renderInlineMarkdown(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  // 匹配 **粗体**、*斜体*、`行内代码`
  const regex = /(\*\*(.+?)\*\*)|(\*(.+?)\*)|(`(.+?)`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    // 前面的普通文本
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    if (match[2]) {
      // **粗体**
      parts.push(
        <Text key={`b-${match.index}`} style={{ fontWeight: '700' }}>
          {match[2]}
        </Text>
      );
    } else if (match[4]) {
      // *斜体*
      parts.push(
        <Text key={`i-${match.index}`} style={{ fontStyle: 'italic' }}>
          {match[4]}
        </Text>
      );
    } else {
      // `行内代码`——正则三分组(粗体|斜体|代码)每次命中必占其一, match[6]条件不可达;
      // else替代else if(match[6])消除死分支, 行为等价(不匹配时原逻辑也是不push)
      parts.push(
        <Text
          key={`c-${match.index}`}
          style={mdStyles.inlineCode}
        >
          {match[6]}
        </Text>
      );
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.length > 0 ? parts : [text];
}

const mdStyles = StyleSheet.create({
  h1: { fontSize: 20, fontWeight: '700', color: '#fff', marginBottom: 4, marginTop: 8 },
  h2: { fontSize: 18, fontWeight: '700', color: '#fff', marginBottom: 4, marginTop: 8 },
  h3: { fontSize: 16, fontWeight: '600', color: '#fff', marginBottom: 4, marginTop: 6 },
  paragraph: { fontSize: 15, color: '#ddd', lineHeight: 22 },
  listItem: { flexDirection: 'row', marginBottom: 2, paddingLeft: 4 },
  bullet: { fontSize: 15, color: '#4ECDC4', width: 20 },
  listText: { fontSize: 15, color: '#ddd', lineHeight: 22, flex: 1 },
  codeBlock: {
    backgroundColor: '#111827',
    borderRadius: 8,
    padding: 12,
    marginVertical: 4,
  },
  codeText: {
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    fontSize: 13,
    color: '#a5d6ff',
  },
  inlineCode: {
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    fontSize: 13,
    color: '#a5d6ff',
    backgroundColor: '#1a1a2e',
    borderRadius: 3,
    paddingHorizontal: 4,
  },
});

// =====================
// 打字动画指示器
// =====================

function TypingIndicator() {
  const [dots, setDots] = useState('');

  useEffect(() => {
    const timer = setInterval(() => {
      setDots((prev) => (prev.length >= 3 ? '' : prev + '.'));
    }, 400);
    return () => clearInterval(timer);
  }, []);

  return (
    <View style={typingStyles.container}>
      <View style={typingStyles.bubble}>
        <View style={typingStyles.dots}>
          <View style={[typingStyles.dot, { opacity: dots.length >= 1 ? 1 : 0.3 }]} />
          <View style={[typingStyles.dot, { opacity: dots.length >= 2 ? 1 : 0.3 }]} />
          <View style={[typingStyles.dot, { opacity: dots.length >= 3 ? 1 : 0.3 }]} />
        </View>
      </View>
    </View>
  );
}

const typingStyles = StyleSheet.create({
  container: { paddingHorizontal: 16, paddingVertical: 4, alignItems: 'flex-start' },
  bubble: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    borderBottomLeftRadius: 4,
    paddingHorizontal: 16,
    paddingVertical: 12,
    maxWidth: '80%',
  },
  dots: { flexDirection: 'row', gap: 4 },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#4ECDC4',
  },
});

// =====================
// 消息气泡组件
// =====================

interface MessageBubbleProps {
  message: ChatMessage;
}

function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <View
      style={[
        bubbleStyles.container,
        isUser ? bubbleStyles.userContainer : bubbleStyles.assistantContainer,
      ]}
    >
      {!isUser && (
        <View style={bubbleStyles.avatar}>
          <Text style={bubbleStyles.avatarText}>AI</Text>
        </View>
      )}
      <View
        style={[
          bubbleStyles.bubble,
          isUser ? bubbleStyles.userBubble : bubbleStyles.assistantBubble,
        ]}
      >
        {isUser ? (
          <Text style={bubbleStyles.userText}>{message.content}</Text>
        ) : message.content ? (
          <View style={bubbleStyles.markdownContent}>
            {renderMarkdown(message.content)}
          </View>
        ) : (
          <Text style={bubbleStyles.assistantText}>正在查询数据…</Text>
        )}
      </View>
    </View>
  );
}

const bubbleStyles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 4,
  },
  userContainer: { justifyContent: 'flex-end' },
  assistantContainer: { justifyContent: 'flex-start', alignItems: 'flex-start' },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#4ECDC4',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 8,
  },
  avatarText: { fontSize: 12, fontWeight: '700', color: '#0f0f23' },
  bubble: {
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 10,
    maxWidth: '78%',
  },
  userBubble: {
    backgroundColor: '#4ECDC4',
    borderBottomRightRadius: 4,
  },
  assistantBubble: {
    backgroundColor: '#1a1a2e',
    borderBottomLeftRadius: 4,
  },
  userText: { fontSize: 15, color: '#0f0f23', lineHeight: 22 },
  assistantText: { fontSize: 15, color: '#ddd', lineHeight: 22 },
  markdownContent: {},
});

// =====================
// AIChatPanel 主组件
// =====================

interface AIChatPanelProps {
  onClose?: () => void;
}

export default function AIChatPanel({ onClose }: AIChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        '你好！我是天链V3的 AI 助手 🤖\n\n我可以帮你：\n- 查询设备状态和遥测数据\n- 查看告警和工单列表\n- 了解营收统计\n- 获取仪表盘概览\n\n请随时问我任何问题！',
      timestamp: Date.now(),
    },
  ]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const flatListRef = useRef<FlatList>(null);
  const inputRef = useRef<TextInput>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => {
      if (mountedRef.current) flatListRef.current?.scrollToEnd({ animated: true });
    }, 100);
  }, []);

  const handleSend = useCallback(async () => {
    const text = inputText.trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText('');
    setLoading(true);
    scrollToBottom();

    // 用于流式更新的临时消息
    let streamedContent = '';
    const assistantMsgId = `assistant-${Date.now()}`;

    // 先添加一个占位消息
    setMessages((prev) => [
      ...prev,
      {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
      },
    ]);

    try {
      const result = await chat(
        [userMsg],
        (token: string) => {
          streamedContent += token;
          // 实时更新最后一条消息
          setMessages((prev) => {
            const updated = [...prev];
            const lastIdx = updated.length - 1;
            if (updated[lastIdx]?.id === assistantMsgId) {
              updated[lastIdx] = {
                ...updated[lastIdx],
                content: streamedContent,
              };
            }
            return updated;
          });
        }
      );

      // 替换占位消息为最终结果; 空回复兜底占位文案——否则气泡渲染走content空分支,
      // "正在查询数据…"永久滞留误导用户(请求已结束但UI仍显示查询中)
      const finalResult =
        result.content && result.content.trim() !== ''
          ? result
          : { ...result, content: '(暂无回复内容)' };
      setMessages((prev) => {
        const updated = [...prev];
        const lastIdx = updated.length - 1;
        if (updated[lastIdx]?.id === assistantMsgId) {
          updated[lastIdx] = finalResult;
        }
        return updated;
      });
    } catch (error) {
      setMessages((prev) => {
        const updated = [...prev];
        const lastIdx = updated.length - 1;
        if (updated[lastIdx]?.id === assistantMsgId) {
          updated[lastIdx] = {
            id: assistantMsgId,
            role: 'assistant',
            content: `抱歉，出错了：${error instanceof Error ? error.message : '未知错误'}`,
            timestamp: Date.now(),
          };
        }
        return updated;
      });
    } finally {
      setLoading(false);
      scrollToBottom();
    }
  }, [inputText, loading, scrollToBottom]);

  // 快捷提问
  const quickQuestions = [
    '仪表盘概览',
    '未处理的告警',
    '今日营收',
    '待处理工单',
  ];


  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      {/* 顶部栏 */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <View style={styles.headerAvatar}>
            <Text style={styles.headerAvatarText}>AI</Text>
          </View>
          <View>
            <Text style={styles.headerTitle}>AI 助手</Text>
            <Text style={styles.headerSubtitle}>天链V3 智能运维</Text>
          </View>
        </View>
        {onClose && (
          <TouchableOpacity onPress={onClose} style={styles.closeButton} accessibilityRole="button" hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
            <Text style={styles.closeText}>✕</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* 消息列表 */}
      <FlatList
        ref={flatListRef}
        data={messages}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => <MessageBubble message={item} />}
        contentContainerStyle={styles.messageList}
        onContentSizeChange={scrollToBottom}
        ListFooterComponent={loading ? <TypingIndicator /> : null}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyText}>开始对话吧</Text>
          </View>
        }
      />

      {/* 快捷提问 */}
      {messages.length <= 1 && !loading && (
        <View style={styles.quickQuestions}>
          {quickQuestions.map((q) => (
            <TouchableOpacity
              key={q}
              style={styles.quickChip}
              onPress={() => {
                setInputText(q);
                // Auto-send on next render cycle
                setTimeout(() => {
                  if (mountedRef.current && q === '仪表盘概览') {
                    setInputText(q);
                    // trigger send via ref
                    inputRef.current?.focus();
                  }
                }, 50);
              }}
             accessibilityRole="button">
              <Text style={styles.quickChipText}>{q}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {/* 输入栏 */}
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={90}
      >
        <View style={styles.inputBar}>
          <TextInput
            ref={inputRef}
            style={styles.textInput}
            value={inputText}
            onChangeText={setInputText}
            placeholder="输入你的问题…"
            placeholderTextColor="#666"
            multiline
            maxLength={500}
            editable={!loading}
            onSubmitEditing={handleSend}
            returnKeyType="send"
          />
          <TouchableOpacity
            style={[
              styles.sendButton,
              (!inputText.trim() || loading) && styles.sendButtonDisabled,
            ]}
            onPress={handleSend}
            disabled={!inputText.trim() || loading}
           accessibilityRole="button"
           hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            {loading ? (
              <ActivityIndicator size="small" color="#0f0f23" />
            ) : (
              <Text style={styles.sendIcon}>↑</Text>
            )}
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// =====================
// 样式
// =====================

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f23' },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#1a1a2e',
    borderBottomWidth: 1,
    borderBottomColor: '#222',
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  headerAvatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#4ECDC4',
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerAvatarText: { fontSize: 14, fontWeight: '700', color: '#0f0f23' },
  headerTitle: { fontSize: 17, fontWeight: '600', color: '#fff' },
  headerSubtitle: { fontSize: 12, color: '#888' },
  closeButton: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#333',
    justifyContent: 'center',
    alignItems: 'center',
  },
  closeText: { fontSize: 14, color: '#fff' },
  messageList: { flexGrow: 1, paddingVertical: 8 },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 80,
  },
  emptyText: { fontSize: 16, color: '#666' },
  quickQuestions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: 16,
    paddingBottom: 8,
    gap: 8,
  },
  quickChip: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: '#333',
  },
  quickChipText: { fontSize: 13, color: '#4ECDC4' },
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: '#1a1a2e',
    borderTopWidth: 1,
    borderTopColor: '#222',
    gap: 8,
  },
  textInput: {
    flex: 1,
    backgroundColor: '#0f0f23',
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 15,
    color: '#fff',
    maxHeight: 100,
  },
  sendButton: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: '#4ECDC4',
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendButtonDisabled: {
    backgroundColor: '#333',
  },
  sendIcon: {
    fontSize: 20,
    color: '#0f0f23',
    fontWeight: '700',
  },
});

export { AIChatPanel }; // named export for consistency