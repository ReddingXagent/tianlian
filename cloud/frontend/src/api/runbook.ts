/**
 * Runbook自动化执行 API
 */
import request from './index';

export interface RunbookTemplate {
  name: string;
  category: string;
  description: string;
  step_count: number;
  auto_steps: number;
  manual_steps: number;
}

export interface RunbookTemplateDetail extends RunbookTemplate {
  steps: Array<{
    step_id: number;
    action_type: string;
    description: string;
    risk_level: string;
    auto_execute: boolean;
    timeout_sec: number;
  }>;
}

export interface RunbookExecution {
  id: number;
  runbook_id: string;
  alarm_id: number;
  device_id: number;
  station_id: number;
  fault_type: string;
  status: string;
  total_duration_ms: number;
  success_steps: number;
  failed_steps: number;
  auto_executed: number;
  manual_required: number;
  created_at: string;
}

export interface RunbookExecutionDetail extends RunbookExecution {
  diagnosis_record_id: number | null;
  steps: any[];
  start_time: string | null;
  end_time: string | null;
  skipped_steps: number;
  workorder_id: number | null;
  error_message: string;
}

export interface RunbookStats {
  total_executions: number;
  status_breakdown: Record<string, number>;
  average_duration_ms: number;
  success_rate: number;
  last_7_days: number;
}

const runbookApi = {
  /** 查询Runbook模板列表 */
  listTemplates: async (category?: string): Promise<RunbookTemplate[]> => {
    const params = category ? { category } : {};
    return request.get('/runbook/templates', { params });
  },

  /** 获取单个Runbook模板详情 */
  getTemplate: async (name: string): Promise<RunbookTemplateDetail> => {
    return request.get(`/runbook/templates/${name}`);
  },

  /** 为告警执行Runbook */
  execute: async (alarmId: number, dryRun = false): Promise<any> => {
    return request.post(`/runbook/execute/${alarmId}`, null, {
      params: { dry_run: dryRun },
    });
  },

  /** 查询执行记录 */
  listExecutions: async (params?: {
    station_id?: number;
    device_id?: number;
    alarm_id?: number;
    status?: string;
    page?: number;
    page_size?: number;
  }): Promise<{ items: RunbookExecution[]; total: number; page: number; page_size: number }> => {
    return request.get('/runbook/executions', { params });
  },

  /** 获取执行详情 */
  getExecution: async (id: number): Promise<RunbookExecutionDetail> => {
    return request.get(`/runbook/executions/${id}`);
  },

  /** 获取Runbook统计 */
  getStats: async (): Promise<RunbookStats> => {
    return request.get('/runbook/stats');
  },
};

export default runbookApi;
