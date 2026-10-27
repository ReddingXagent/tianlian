/**
 * 智能诊断 API
 *
 * 复用 src/api/index.ts 的共享 axios 实例，继承请求拦截器（Authorization
 * Bearer token + X-Team-Id 团队隔离）与响应拦截器（{code,data,message} 解套 + 401 处理）。
 */
import api from './index';

export interface DiagnosisResult {
  device_id: number;
  device_name: string;
  device_sn: string;
  device_type: string;
  station_name: string;
  overall_health: number;
  diagnosis_time: string;
  scores: {
    electrical_safe: number;
    thermal: number;
    communication: number;
    power_quality: number;
    mechanical: number;
  };
  analysis: Array<{
    category: string;
    issue: string;
    severity: string;
    score?: number;
    action?: string;
  }>;
  risk_level: string;
  recommendations: Array<{
    priority: string;
    category: string;
    action: string;
    reason: string;
  }>;
  predicted_failures: Array<{
    type: string;
    probability: string;
    preventive_action: string;
  }>;
  estimated_cost: {
    min: number;
    max: number;
  };
  workorder_stats: {
    total: number;
    pending: number;
    completed: number;
  };
  alarm_stats: {
    total: number;
    active: number;
    critical: number;
  };
}

export interface BatchDiagnosisResult {
  total_devices: number;
  healthy_devices: number;
  warning_devices: number;
  fault_devices: number;
  critical_devices: number;
  avg_health_score: number;
  top_issues: Array<{
    device_name: string;
    health_score: number;
    alarm_count: number;
    status: string;
  }>;
  summary: {
    health_rate: number;
    risk_devices: number;
  };
}

export interface HealthTrendData {
  device_id: number;
  device_name: string;
  trend_data: Array<{
    date: string;
    total_score: number;
    electrical: number;
    thermal: number;
    communication: number;
    power_quality: number;
    mechanical: number;
  }>;
  summary: {
    start_score: number;
    end_score: number;
    change: number;
  };
}

export const diagnosisAPI = {
  /**
   * 单设备诊断
   */
  diagnoseDevice: async (deviceId: number, includeHistory = true): Promise<DiagnosisResult> => {
    const response = await api.post('/diagnosis/device', {
      device_id: deviceId,
      include_history: includeHistory,
    });
    return response.data;
  },

  /**
   * 批量诊断
   */
  diagnoseBatch: async (params: {
    station_id?: number;
    device_type?: string;
    min_health_score?: number;
  }): Promise<BatchDiagnosisResult> => {
    const response = await api.post('/diagnosis/batch', params);
    return response.data;
  },

  /**
   * 获取健康度趋势
   */
  getHealthTrend: async (deviceId: number, days = 30): Promise<HealthTrendData> => {
    const response = await api.get(`/diagnosis/health-trend/${deviceId}`, {
      params: { days },
    });
    return response.data;
  },

  /**
   * 站点诊断摘要
   */
  getStationSummary: async (stationId: number): Promise<any> => {
    const response = await api.get(`/diagnosis/station-summary/${stationId}`);
    return response.data;
  },
};

export default diagnosisAPI;