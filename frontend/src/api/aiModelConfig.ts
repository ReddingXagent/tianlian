import api from './index';

export interface ProviderConfig {
  provider: string;
  model_id: string;
  name: string;
  base_url: string;
  api_key?: string;
  context_window: number;
  max_tokens: number;
  enabled: boolean;
}

export interface AIModelFullConfig {
  providers: ProviderConfig[];
  task_mappings: Record<string, string>;
  fallback_strategy: string;
}

const TASK_LABELS: Record<string, string> = {
  log_analysis: '日志分析',
  fault_classify: '故障分类',
  root_cause: '根因分析',
  repair_suggest: '维修建议',
  preventive: '预防措施',
  chat_general: '通用对话',
};

export function getTaskLabel(taskType: string): string {
  return TASK_LABELS[taskType] || taskType;
}

export const aiModelConfigAPI = {
  getConfig: () => api.get('/ai-model_config'),
  updateConfig: (data: AIModelFullConfig) => api.put('/ai-model_config', data),
  updateProviders: (providers: ProviderConfig[]) => api.put('/ai-model_config/providers', providers),
  updateTaskMappings: (mappings: Record<string, string>) => api.put('/ai-model_config/task-mappings', { mappings }),
};