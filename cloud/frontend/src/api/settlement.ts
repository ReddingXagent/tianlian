/**
 * 运营结算对账 + 发票管理 API 层
 *
 * 对应后端:
 *   backend/app/api/v1/operate/ops_settlement.py
 *   backend/app/api/v1/operate/ops_invoice.py (仅 titles 族保留; 发票本体族已 deprecated, 卡 6d06831d)
 *   backend/app/api/v1/operate/ops_invoice_request.py (InvoiceRequest 新体系)
 */
import api from './index';

/* ── 日结汇总 ── */
export const dailySettlementAPI = {
  list: (params?: {
    start_date?: string;
    end_date?: string;
    station_id?: number;
    status?: string;
    page?: number;
    page_size?: number;
  }) => api.get('/operate/settlement/daily', { params }),

  get: (id: number) => api.get(`/operate/settlement/daily/${id}`),

  generate: (data: {
    settlement_date: string;
    station_id?: number;
    total_orders?: number;
    total_charge_fee?: number;
    total_service_fee?: number;
    total_amount?: number;
    total_paid?: number;
    remark?: string;
  }) => api.post('/operate/settlement/daily/generate', data),

  confirm: (id: number) => api.put(`/operate/settlement/daily/${id}/confirm`),
};

/* ── 支付对账 ── */
export const reconciliationAPI = {
  list: (params?: {
    start_date?: string;
    end_date?: string;
    payment_channel?: string;
    status?: string;
    page?: number;
    page_size?: number;
  }) => api.get('/operate/settlement/reconciliation', { params }),

  create: (data: {
    settlement_date: string;
    payment_channel: string;
    platform_orders_count?: number;
    platform_amount?: number;
    payment_orders_count?: number;
    payment_amount?: number;
    difference_count?: number;
    difference_amount?: number;
    difference_detail?: string;
  }) => api.post('/operate/settlement/reconciliation', data),

  reconcile: (id: number, data: { operator?: string; difference_detail?: string }) =>
    api.put(`/operate/settlement/reconciliation/${id}/reconcile`, data),
};

/* ── 企业结算 ── */
export const enterpriseSettlementAPI = {
  list: (params?: { page?: number; page_size?: number }) =>
    api.get('/operate/settlement/enterprise', { params }),
};

/* ── 互联互通结算 ── */
export const interconnectAPI = {
  list: (params?: {
    platform_id?: string;
    status?: string;
    page?: number;
    page_size?: number;
  }) => api.get('/operate/settlement/interconnect', { params }),

  create: (data: {
    platform_id: string;
    platform_name?: string;
    start_date: string;
    end_date: string;
    total_orders?: number;
    total_amount?: number;
    revenue_share_ratio?: string;
  }) => api.post('/operate/settlement/interconnect', data),

  settle: (id: number, data: { operator?: string }) =>
    api.put(`/operate/settlement/interconnect/${id}/settle`, data),
};

/* ── 发票抬头 ── */
export const invoiceTitleAPI = {
  list: (params?: {
    title_type?: string;
    page?: number;
    page_size?: number;
  }) => api.get('/operate/invoices/titles', { params }),

  create: (data: {
    title_type?: string;
    title_name: string;
    tax_id?: string;
    register_address?: string;
    register_phone?: string;
    bank_name?: string;
    bank_account?: string;
    email?: string;
    is_default?: boolean;
  }) => api.post('/operate/invoices/titles', data),

  update: (id: number, data: Record<string, unknown>) =>
    api.put(`/operate/invoices/titles/${id}`, data),

  delete: (id: number) => api.delete(`/operate/invoices/titles/${id}`),
};

/* ── 第三方开票平台配置 ── */
export const invoicePlatformAPI = {
  list: (params: {
    team_id: number;
    platform_type?: string;
    enabled?: boolean;
  }) => api.get('/operate/invoice-platforms', { params }),

  create: (data: {
    team_id: number;
    platform_type: string;
    platform_name: string;
    api_url?: string;
    app_key?: string;
    app_secret?: string;
    taxpayer_id?: string;
    tax_classification_code?: string;
    is_default?: boolean;
    enabled?: boolean;
    remark?: string;
  }) => api.post('/operate/invoice-platforms', data),

  update: (id: number, data: Partial<{
    platform_type: string;
    platform_name: string;
    api_url: string;
    app_key: string;
    app_secret: string;
    taxpayer_id: string;
    tax_classification_code: string;
    is_default: boolean;
    enabled: boolean;
    remark: string;
  }>) => api.put(`/operate/invoice-platforms/${id}`, data),

  delete: (id: number) => api.delete(`/operate/invoice-platforms/${id}`),

  setDefault: (id: number) => api.put(`/operate/invoice-platforms/${id}/default`),
};

/* ── 旧 OpsInvoice API 已删除 (卡 6d06831d, B1 下线旧体系) ──
 * 后端 /operate/invoices* (发票本体族) 已标 deprecated;
 * 列表/审核/开具统一走下方 opsInvoiceRequestAPI (契约 v1.3 §5.4)。
 */

/* ── 手动开票申请 (卡 a09f8a21 契约 §5.4) ──
 * C端用户申请 → 运营 /ops/invoice-requests 列表 + 上传发票文件 + 拒绝。
 * 金额单位: 分 (契约 §6); 前端展示按 /100 折算为元。
 */
export const opsInvoiceRequestAPI = {
  list: (params?: { status?: string; page?: number; page_size?: number }) =>
    api.get('/ops/invoice-requests', { params }),

  upload: (id: number, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api.post(`/ops/invoice-requests/${id}/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  reject: (id: number, data: { reject_reason: string }) =>
    api.post(`/ops/invoice-requests/${id}/reject`, data),

  /* 红冲已开发票 (卡 f42bdf5a, R1 方案b: status 保持 issued, 打 voided 标记) */
  void: (id: number, data: { reason: string }) =>
    api.post(`/ops/invoice-requests/${id}/void`, data),
};
