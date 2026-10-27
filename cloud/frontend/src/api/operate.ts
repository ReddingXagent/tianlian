/**
 * 运营管理 - 订单 + 退款 API 层
 *
 * 对应后端:
 *   backend/app/api/v1/operate/orders.py
 *   backend/app/api/v1/order_fees.py
 */
import api from './index';

/* ── 订单管理 ── */
export const operateOrderAPI = {
  /** 通用订单列表(多维度筛选) */
  list: (params?: {
    status?: string;
    payment_status?: string;
    station_id?: number;
    keyword?: string;
    start_date?: string;
    end_date?: string;
    page?: number;
    page_size?: number;
  }) => api.get('/operate/orders', { params }),

  /** 订单详情(费用明细) */
  getFeeItems: (orderId: number) =>
    api.get(`/orders/${orderId}/fee-items`),

  /** 订单充电曲线(功率/电量/SOC 时间序列) */
  getChargeCurve: (orderId: number) =>
    api.get(`/operate/orders/${orderId}/charge-curve`),

  /** 订单退款记录 */
  getRefunds: (orderId: number) =>
    api.get(`/orders/${orderId}/refunds`),

  /** 企业充电订单 */
  listEnterprise: (params?: { enterprise_id?: number; page?: number; page_size?: number }) =>
    api.get('/operate/orders/enterprise', { params }),

  /** 车辆充电订单 */
  listVehicle: (params?: { plate_number?: string; page?: number; page_size?: number }) =>
    api.get('/operate/orders/vehicle', { params }),

  /** 标记异常订单已处理 (卡 f730f63c) */
  resolve: (orderId: number, data: {
    handle_type: 'refunded' | 'written_off' | 'false_alarm';
    remark?: string;
  }) => api.post(`/operate/orders/${orderId}/resolve`, data),

  /** 重试计费 — 仅 failed 订单 (卡 f730f63c) */
  retryCharge: (orderId: number) =>
    api.post(`/operate/orders/${orderId}/retry-charge`),
};

/* ── 退款管理 ── */
export const refundAPI = {
  /** 全局退款记录列表 (卡 34ec1d55) — 跨订单分页, 替代逐单 N+1 拉取 */
  listAll: (params?: { status?: string; page?: number; page_size?: number }) =>
    api.get('/orders/refunds', { params }),

  /** 发起退款申请 */
  create: (orderId: number, data: { refund_amount: number; reason: string }) =>
    api.post(`/orders/${orderId}/refund`, data),

  /** 审批通过 */
  approve: (orderId: number, refundId: number, data: { reviewer_id: number }) =>
    api.post(`/orders/${orderId}/refunds/${refundId}/approve`, data),

  /** 拒绝退款 */
  reject: (orderId: number, refundId: number, data: { reviewer_id: number; reject_reason?: string }) =>
    api.post(`/orders/${orderId}/refunds/${refundId}/reject`, data),

  /** 标记退款完成 */
  complete: (orderId: number, refundId: number) =>
    api.post(`/orders/${orderId}/refunds/${refundId}/complete`),
};

/* ── 充电桩二维码 ── */
// 对应后端: backend/app/api/v1/operate/charger_qrcode.py
export const chargerQRCodeAPI = {
  /** 充电桩二维码列表(分页 / 按站点筛选) */
  list: (params?: { station_id?: number; page?: number; page_size?: number }) =>
    api.get('/operate/charger-qrcode/list', { params }),

  /** 生成二维码(单张 / 批量) — 入参 device_ids */
  generate: (data: { device_ids: number[]; org_code?: string }) =>
    api.post('/operate/charger-qrcode/generate', data),

  /** 下载单张二维码 PNG (blob, 需带鉴权 header 故走 axios) */
  downloadSingle: (deviceId: number) =>
    api.get(`/operate/charger-qrcode/download/${deviceId}`, { responseType: 'blob' }),

  /** 批量打包 ZIP 下载 (blob) */
  batchDownload: (data: { device_ids: number[] }) =>
    api.post('/operate/charger-qrcode/batch-download', data, { responseType: 'blob' }),
};
