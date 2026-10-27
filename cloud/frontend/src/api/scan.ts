/**
 * 扫码报修 API
 *
 * 复用 src/api/index.ts 的共享 axios 实例，继承请求拦截器（Authorization
 * Bearer token + X-Team-Id 团队隔离）与响应拦截器（{code,data,message} 解套 + 401 处理）。
 */
import api from './index';

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
  last_maintenance?: string;
  qr_code: string;
}

export interface QuickRepairRequest {
  device_id: number;
  fault_desc: string;
  fault_level?: string;
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
  message: string;
}

export const scanAPI = {
  /**
   * 扫码识别设备
   */
  scanDevice: (qrCode: string) => 
    api.post<ScanResult>('/scan/device', { qr_code: qrCode }),

  /**
   * 快速报修
   */
  quickRepair: (data: QuickRepairRequest) => 
    api.post<QuickRepairResult>('/scan/quick-repair', data),

  /**
   * 生成设备二维码
   */
  generateQRCode: (data: QRCodeGenerateRequest) => 
    api.post<QRCodeGenerateResult>('/scan/qrcode/generate', data),

  /**
   * 获取设备二维码
   */
  getDeviceQRCode: (deviceId: number) => 
    api.get(`/scan/qrcode/${deviceId}`),

  /**
   * 获取二维码列表
   */
  listQRCodes: (page?: number, pageSize?: number, deviceId?: number) => 
    api.get('/scan/qrcodes', { params: { page, page_size: pageSize, device_id: deviceId } }),

  /**
   * 删除/禁用二维码
   */
  deleteQRCode: (deviceId: number) => 
    api.delete(`/scan/qrcode/${deviceId}`),
};

export default scanAPI;