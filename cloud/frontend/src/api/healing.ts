/**
 * 告警自愈引擎 API
 */
import request from './index';

// ========== 类型定义 ==========

export interface HealingRule {
  id: number;
  name: string;
  description: string;
  alarm_pattern: {
    alarm_levels?: string[];
    alarm_types?: string[];
    device_types?: string[];
    device_ids?: number[];
    station_ids?: number[];
    content_keywords?: string[];
  };
  runbook_template: string | null;
  auto_approve: boolean;
  max_retries: number;
  cooldown_minutes: number;
  priority: number;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface HealingExecution {
  id: number;
  rule_id: number;
  rule_name: string;
  alarm_id: number;
  device_id: number;
  station_id: number;
  runbook_id: string | null;
  fault_type: string;
  status: string;
  approved_by: string | null;
  total_duration_ms: number;
  success_steps: number;
  failed_steps: number;
  retry_count: number;
  result: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface HealingExecutionDetail extends HealingExecution {
  runbook_template: string | null;
  steps: any[];
  approved_at: string | null;
  reject_reason: string | null;
  error_message: string | null;
}

export interface HealingStats {
  total: number;
  status_breakdown: Record<string, number>;
  success_rate: number;
  average_duration_ms: number;
  auto_approve_rate: number;
  pending_approvals: number;
}

// ========== API ==========

const healingApi = {
  /** 列出自愈规则 */
  listRules: async (enabledOnly = false): Promise<HealingRule[]> => {
    return request.get('/healing/rules', { params: { enabled_only: enabledOnly } });
  },

  /** 获取规则详情 */
  getRule: async (id: number): Promise<HealingRule> => {
    return request.get(`/healing/rules/${id}`);
  },

  /** 创建规则 */
  createRule: async (data: Partial<HealingRule>): Promise<any> => {
    return request.post('/healing/rules', data);
  },

  /** 更新规则 */
  updateRule: async (id: number, data: Partial<HealingRule>): Promise<any> => {
    return request.put(`/healing/rules/${id}`, data);
  },

  /** 删除规则 */
  deleteRule: async (id: number): Promise<any> => {
    return request.delete(`/healing/rules/${id}`);
  },

  /** 查询执行记录 */
  listExecutions: async (params?: {
    status?: string;
    rule_id?: number;
    device_id?: number;
    page?: number;
    page_size?: number;
  }): Promise<{ items: HealingExecution[]; total: number; page: number; page_size: number }> => {
    return request.get('/healing/executions', { params });
  },

  /** 获取执行详情 */
  getExecution: async (id: number): Promise<HealingExecutionDetail> => {
    return request.get(`/healing/executions/${id}`);
  },

  /** 审批通过 */
  approveExecution: async (id: number): Promise<any> => {
    return request.post(`/healing/executions/${id}/approve`);
  },

  /** 拒绝执行 */
  rejectExecution: async (id: number, reason?: string): Promise<any> => {
    return request.post(`/healing/executions/${id}/reject`, { reason: reason || '' });
  },

  /** 重试执行 */
  retryExecution: async (id: number): Promise<any> => {
    return request.post(`/healing/executions/${id}/retry`);
  },

  /** 手动触发自愈评估 */
  triggerHealing: async (alarmId: number): Promise<any> => {
    return request.post(`/healing/trigger/${alarmId}`);
  },

  /** 获取自愈统计 */
  getStats: async (): Promise<HealingStats> => {
    return request.get('/healing/stats');
  },
};

export default healingApi;
