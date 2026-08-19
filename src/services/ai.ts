/**
 * AI 助手服务
 *
 * 对接云端 AI API (/api/v1/chat)，简单对话格式 {message}→{answer}。
 * 原OpenAI兼容格式(/ai/chat)已下线, 2026-08-20适配新端点。
 *
 * @module services/ai
 */

import api, {
  deviceApi,
  alarmApi,
  workOrderApi,
  dashboardApi,
  revenueApi,
  tokenStorage,
} from './api';
import type {
  AlarmStatus,
  WorkOrderStatus,
  Alarm,
  WorkOrder,
  DashboardStats,
  RevenueRecord,
} from '../types';

// =====================
// 类型定义
// =====================

/** 聊天消息 */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  toolCalls?: ToolCall[];
  toolCallId?: string;
  timestamp: number;
}

/** AI 工具调用请求 */
export interface ToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string;
  };
}

/** 工具执行结果 */
export interface ToolResult {
  toolCallId: string;
  role: 'tool';
  content: string;
}

/** AI 对话请求 */
export interface ChatRequest {
  messages: Pick<ChatMessage, 'role' | 'content'>[];
  stream?: boolean;
  functions?: FunctionDefinition[];
}

/** AI 对话响应（非流式） */
export interface ChatResponse {
  id: string;
  choices: {
    message: {
      role: 'assistant';
      content: string | null;
      toolCalls?: ToolCall[];
    };
    finishReason: 'stop' | 'tool_calls' | 'length';
  }[];
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
}

/** 流式响应的 chunk */
export interface ChatStreamChunk {
  id: string;
  choices: {
    delta: {
      role?: string;
      content?: string;
      toolCalls?: {
        index: number;
        id?: string;
        type?: 'function';
        function?: {
          name?: string;
          arguments?: string;
        };
      }[];
    };
    finishReason?: 'stop' | 'tool_calls' | 'length';
  }[];
}

/** Function 定义（OpenAI 兼容格式） */
export interface FunctionDefinition {
  name: string;
  description: string;
  parameters: {
    type: 'object';
    properties: Record<string, {
      type: string;
      description: string;
      enum?: string[];
    }>;
    required?: string[];
  };
}

// =====================
// 系统提示词
// =====================

// eslint-disable-next-line @typescript-eslint/no-unused-vars -- 保留系统提示词, 待云端AI上线function calling后启用
const SYSTEM_PROMPT = `你是天链V3充电站管理系统的 AI 助手，专门为站长提供智能运维服务。

你的核心能力：
- 查询充电站设备状态、告警信息、工单进度、营收数据
- 提供设备故障诊断建议和运维指导
- 分析营收趋势，辅助经营决策
- 协助生成运维报告和工单

回答原则：
1. 使用中文回复，简洁专业
2. 当用户询问具体数据时，调用相应的 function 获取最新数据
3. 当回复中包含数字金额时，以元为单位显示（保留两位小数）
4. 对于设备控制操作，务必先确认风险再执行
5. 不要编造数据，如果无法获取则如实告知`;

// =====================
// AI 工具定义（Function Calling）
// =====================

/** 可调用的工具函数列表 */
export const AI_FUNCTIONS: FunctionDefinition[] = [
  {
    name: 'get_device_status',
    description: '查询指定设备的实时状态和遥测数据，包括功率、电压、电流、温度等',
    parameters: {
      type: 'object',
      properties: {
        device_id: {
          type: 'number',
          description: '设备ID',
        },
      },
      required: ['device_id'],
    },
  },
  {
    name: 'list_alarms',
    description: '查询告警列表，可按状态筛选',
    parameters: {
      type: 'object',
      properties: {
        status: {
          type: 'string',
          description: '告警状态筛选：unhandled（未处理）、processing（处理中）、resolved（已解决），不传则返回全部',
          enum: ['unhandled', 'processing', 'resolved'],
        },
      },
    },
  },
  {
    name: 'list_workorders',
    description: '查询工单列表，可按状态筛选',
    parameters: {
      type: 'object',
      properties: {
        status: {
          type: 'string',
          description: '工单状态筛选：pending（待处理）、in_progress（进行中）、completed（已完成）、cancelled（已取消），不传则返回全部',
          enum: ['pending', 'in_progress', 'completed', 'cancelled'],
        },
      },
    },
  },
  {
    name: 'get_revenue_stats',
    description: '查询营收统计数据，支持按日、周、月查询',
    parameters: {
      type: 'object',
      properties: {
        period: {
          type: 'string',
          description: '统计周期：day（今日）、week（本周）、month（本月）',
          enum: ['day', 'week', 'month'],
        },
      },
      required: ['period'],
    },
  },
  {
    name: 'get_dashboard_summary',
    description: '获取仪表盘概览数据，包括站点总数、在线/离线数、告警数、营收摘要',
    parameters: {
      type: 'object',
      properties: {},
    },
  },
  {
    name: 'control_device',
    description: '远程控制设备，支持启动、停止、重启、复位操作。⚠️ 执行前请向用户确认风险',
    parameters: {
      type: 'object',
      properties: {
        device_id: {
          type: 'number',
          description: '设备ID',
        },
        action: {
          type: 'string',
          description: '控制动作',
          enum: ['start', 'stop', 'restart', 'reset'],
        },
      },
      required: ['device_id', 'action'],
    },
  },
];

// =====================
// Function 执行器
// =====================

/**
 * 执行 AI 请求的工具调用
 * 每个 function 封装对现有 api.ts 的调用
 */
export async function executeToolCall(
  name: string,
  args: Record<string, unknown>
): Promise<string> {
  try {
    switch (name) {
      case 'get_device_status': {
        const deviceId = args.device_id as number;
        const [deviceResp, telemetryResp] = await Promise.all([
          deviceApi.getDetail(deviceId),
          deviceApi.getTelemetry(deviceId),
        ]);
        const device = deviceResp.data;
        const telemetry = telemetryResp.data;
        return JSON.stringify({
          device: {
            id: device.id,
            name: device.name,
            type: device.type,
            status: device.status,
            model: device.model,
            lastHeartbeat: device.lastHeartbeat,
          },
          telemetry: {
            power: `${telemetry.power} kW`,
            voltage: `${telemetry.voltage} V`,
            current: `${telemetry.current} A`,
            temperature: `${telemetry.temperature} °C`,
            energy: `${telemetry.energy} kWh`,
            timestamp: telemetry.timestamp,
          },
        });
      }

      case 'list_alarms': {
        const status = args.status as AlarmStatus | undefined;
        const resp = await alarmApi.getList({
          status,
          pageSize: 20,
        });
        const alarms = resp.data.items.map((a: Alarm) => ({
          id: a.id,
          stationName: a.stationName,
          title: a.title,
          level: a.level,
          status: a.status,
          createdAt: a.createdAt,
        }));
        return JSON.stringify({ alarms, total: resp.data.total });
      }

      case 'list_workorders': {
        const status = args.status as WorkOrderStatus | undefined;
        const resp = await workOrderApi.getList({
          status,
          pageSize: 20,
        });
        const orders = resp.data.items.map((o: WorkOrder) => ({
          id: o.id,
          stationName: o.stationName,
          title: o.title,
          priority: o.priority,
          status: o.status,
          assigneeName: o.assigneeName,
          createdAt: o.createdAt,
        }));
        return JSON.stringify({ orders, total: resp.data.total });
      }

      case 'get_revenue_stats': {
        const period = args.period as 'day' | 'week' | 'month';
        if (period === 'day') {
          const resp = await revenueApi.getSummary();
          const summary = resp.data;
          return JSON.stringify({
            today: `¥${summary.today.toFixed(2)}`,
            week: `¥${summary.week.toFixed(2)}`,
            month: `¥${summary.month.toFixed(2)}`,
            total: `¥${summary.total.toFixed(2)}`,
            period,
          });
        }
        // week/month 用 revenue records (金额单位: 元)
        const resp = await revenueApi.getRecords({ type: period });
        const records = resp.data.map((r: RevenueRecord) => ({
          date: r.date,
          amount: `¥${r.amount.toFixed(2)}`,
          orderCount: r.orderCount,
        }));
        return JSON.stringify({ records, period });
      }

      case 'get_dashboard_summary': {
        const resp = await dashboardApi.getStats();
        const stats: DashboardStats = resp.data;
        return JSON.stringify({
          totalStations: stats.totalStations,
          onlineStations: stats.onlineStations,
          offlineStations: stats.offlineStations,
          totalAlarms: stats.totalAlarms,
          unhandledAlarms: stats.unhandledAlarms,
          revenueToday: `¥${(stats.revenueSummary?.today ?? 0).toFixed(2)}`,
          revenueWeek: `¥${(stats.revenueSummary?.week ?? 0).toFixed(2)}`,
          revenueMonth: `¥${(stats.revenueSummary?.month ?? 0).toFixed(2)}`,
        });
      }

      case 'control_device': {
        const deviceId = args.device_id as number;
        const action = args.action as string;
        const resp = await deviceApi.controlDevice(deviceId, action);
        return JSON.stringify(resp.data);
      }

      default:
        return JSON.stringify({ error: `Unknown function: ${name}` });
    }
  } catch (error: unknown) {
    const err = error as Error & { response?: { data?: { message?: string } } };
    const message =
      err?.response?.data?.message || err?.message || 'Unknown error';
    return JSON.stringify({ error: `Failed to execute ${name}: ${message}` });
  }
}

// =====================
// AI 对话 API
// =====================

const AI_CHAT_ENDPOINT = '/chat';

/** 新端点响应类型 (非OpenAI兼容, 简单{message}→{answer}格式) */
interface ChatEndpointResponse {
  code: number;
  message: string;
  data: {
    answer: string;
    confidence: number;
    sources: unknown[];
    actions: unknown[];
    needs_human: boolean;
    usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number } | null;
  };
  timestamp: number;
}

/** 流式chunk类型 (JSON Lines格式, 非SSE) */
interface ChatStreamChunkNew {
  type: 'chunk' | 'done';
  content?: string;
}

/**
 * 非流式对话 — 适配新 /chat 端点
 * 新端点只接受 {message: string}, 不支持 messages 数组/function calling
 */
export async function sendChatMessage(
  messages: ChatMessage[]
): Promise<ChatMessage> {
  // 提取最后一条用户消息 (新端点是单轮对话)
  const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user');
  if (!lastUserMsg) {
    return {
      id: generateId(),
      role: 'assistant',
      content: '请输入您的问题。',
      timestamp: Date.now(),
    };
  }

  const resp = await api.post<ChatEndpointResponse>(AI_CHAT_ENDPOINT, {
    message: lastUserMsg.content,
  });

  const data = resp.data.data;
  return {
    id: generateId(),
    role: 'assistant',
    content: data.answer || '',
    timestamp: Date.now(),
  };
}

/**
 * 流式对话 — 适配新 /chat 端点的 JSON Lines 流格式
 * 格式: {"type":"chunk","content":"..."}\n{"type":"done"}
 */
export async function* streamChatMessage(
  messages: ChatMessage[]
): AsyncGenerator<{ type: string; content?: string }> {
  const token = await tokenStorage.getToken();
  // 提取最后一条用户消息
  const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user');
  if (!lastUserMsg) return;

  const response = await fetch(`${api.defaults.baseURL}${AI_CHAT_ENDPOINT}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      message: lastUserMsg.content,
      stream: true,
    }),
  });

  if (!response.ok) {
    const errorBody = await response.text().catch(() => '');
    throw new Error(`AI API error ${response.status}: ${errorBody}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('Streaming not supported');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        try {
          const chunk: ChatStreamChunkNew = JSON.parse(trimmed);
          if (chunk.type === 'done') return;
          if (chunk.type === 'chunk' && chunk.content) {
            yield chunk;
          }
        } catch {
          // 跳过无法解析的行
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// =====================
// 多轮对话引擎
// =====================

/**
 * 多轮对话引擎 — 适配新 /chat 端点
 * 新端点不支持 function calling, 简化为流式调用 + onToken 回调
 */
export async function chat(
  messages: ChatMessage[],
  onToken?: (text: string) => void
): Promise<ChatMessage> {
  let fullContent = '';

  try {
    for await (const chunk of streamChatMessage(messages)) {
      if (chunk.content) {
        fullContent += chunk.content;
        onToken?.(chunk.content);
      }
    }
  } catch (error) {
    return {
      id: generateId(),
      role: 'assistant',
      content: `抱歉，AI 服务暂时不可用：${error instanceof Error ? error.message : '未知错误'}`,
      timestamp: Date.now(),
    };
  }

  return {
    id: generateId(),
    role: 'assistant',
    content: fullContent || '抱歉，我没有理解您的问题，请换个方式描述。',
    timestamp: Date.now(),
  };
}

// =====================
// 工具函数
// =====================

function generateId(): string {
  return `chatcmpl-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}