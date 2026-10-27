/**
 * types/modules/ai.ts — AI对话类型
 */
export interface ChatSource {
  title: string;
  url: string;
  type: string;
}

export interface ChatAction {
  type: string;
  label: string;
  target: string;
}

export interface ChatUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface ChatResponse {
  answer: string;
  confidence: number;
  sources: ChatSource[];
  actions: ChatAction[];
  needsHuman: boolean;
  usage: ChatUsage | null;
}
