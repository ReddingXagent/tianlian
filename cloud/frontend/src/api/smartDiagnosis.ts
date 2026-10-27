/**
 * 智能故障诊断 API - 前端接口
 */
import request from './index';

// ========== 智能诊断接口 ==========

export interface DiagnosisRequest {
  device_id?: number;
  fault_desc: string;
  fault_keywords?: string[];
}

export interface DiagnosisResult {
  success: boolean;
  fault_type: string;
  fault_level: string;
  possible_causes: string[];
  recommended_actions: string[];
  related_articles: any[];
  auto_create_workorder: boolean;
  confidence: number;
  matched_keywords?: string[];
  device_info?: any;
  message: string;
}

export interface WorkorderInfo {
  workorder_id: string;
  status: string;
  message: string;
}

export interface DiagnosisAndRepairResult extends DiagnosisResult {
  workorder?: WorkorderInfo;
}

// ========== 智能诊断 API ==========

const smartDiagnosisApi = {
  /**
   * 智能故障诊断
   */
  analyze: async (data: DiagnosisRequest): Promise<DiagnosisResult> => {
    return request.post('/smart-diagnosis/analyze', data);
  },

  /**
   * 诊断并自动创建工单
   */
  diagnoseAndRepair: async (data: DiagnosisRequest): Promise<DiagnosisAndRepairResult> => {
    return request.post('/smart-diagnosis/diagnose-and-repair', data);
  },

  /**
   * 获取故障关键词列表
   */
  getKeywords: async (): Promise<any> => {
    return request.get('/smart-diagnosis/keywords');
  },

  /**
   * 查询历史诊断记录
   */
  getHistory: async (params?: { device_id?: number; page?: number; page_size?: number }): Promise<any> => {
    return request.get('/smart-diagnosis/history', { params });
  },
};

export default smartDiagnosisApi;