/**
 * 扫码报修相关类型定义
 */

export interface ScanResult {
  success: boolean;
  device_id: number;
  device_sn: string;
  device_name: string;
  device_type: string;
  device_status: string;
  station_id: number;
  station_name: string;
  station_address: string;
  health_score: number;
  last_maintenance: string | null;
  qr_code: string;
}

export interface QuickRepairRequest {
  device_id: number;
  fault_desc: string;
  fault_level?: 'info' | 'warning' | 'critical';
  contact_name?: string;
  contact_phone?: string;
  attachments?: string[];
}

export interface QuickRepairResult {
  success: boolean;
  workorder_id: string;
  device_name: string;
  station_name: string;
  fault_desc: string;
  status: string;
  create_time: string;
  message: string;
}

export interface QRCodeGenerateRequest {
  device_id: number;
  notes?: string;
}

export interface QRCodeGenerateResult {
  success: boolean;
  qr_code: string;
  qr_image_url: string;
  device_id: number;
  device_name: string;
  message?: string;
}

export interface DeviceQRCodeInfo {
  id: number;
  qr_code: string;
  device_id: number;
  device_name: string;
  device_sn: string;
  scan_count: number;
  is_active: boolean;
  created_at: string;
}