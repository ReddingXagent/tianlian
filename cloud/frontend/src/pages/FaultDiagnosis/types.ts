/**
 * AI 智能诊断 — 类型定义
 */

export interface AIDiagnosisResult {
  fault_type: string;
  fault_location: string;
  root_cause: string;
  severity: string;
  confidence: number;
  possible_causes: string[];
  immediate_actions: string[];
  repair_suggestions: string[];
  preventive_measures: string[];
  remote_fixable: boolean;
}

export interface AnalysisRecord {
  id: number;
  alarm_id: number | null;
  device_id: number;
  status: string;
  trigger_type: string;
  fault_type: string | null;
  fault_location: string | null;
  root_cause: string | null;
  severity: string | null;
  confidence: number | null;
  matched_fault_code: string | null;
  matched_fault_name: string | null;
  immediate_actions: string[] | null;
  repair_suggestions: string[] | null;
  preventive_measures: string[] | null;
  remote_fixable: boolean;
  error_message: string | null;
  duration_ms: number | null;
  created_at: string;
  completed_at: string | null;
}

export interface ModelProvider {
  provider: string;
  model_id: string;
  name: string;
  base_url: string;
  api_key: string;
  enabled: boolean;
}
