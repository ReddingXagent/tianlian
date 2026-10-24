/**
 * 运营平台 - 互联互通 + 市政监管 API 层 (迁移自 admin.ts)
 *
 * 对应后端:
 *   backend/app/api/v1/operate/interconnect.py   互联互通平台管理 + 导流订单
 *   backend/app/api/v1/operate/supervision.py    市政监管配置 + 上报记录 + 合规检查
 */
import api from './index';

/* ── 互联互通平台配置 ── */
export const interconnectAPI = {
  /** 平台配置列表(支持 platform_code/status/keyword 筛选) */
  list: (params?: {
    platform_code?: string;
    status?: string;
    keyword?: string;
    page?: number;
    page_size?: number;
  }) => api.get('/operate/interconnect/configs', { params }),

  get: (id: number) => api.get(`/operate/interconnect/configs/${id}`),
  create: (data: Record<string, unknown>) => api.post('/operate/interconnect/configs', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/operate/interconnect/configs/${id}`, data),
  delete: (id: number) => api.delete(`/operate/interconnect/configs/${id}`),

  /** 联调测试(模拟, 校验地址可达 + 认证可用) */
  test: (id: number) => api.post(`/operate/interconnect/configs/${id}/test`),
};

/* ── 互联互通导流订单 ── */
export const interconnectOrderAPI = {
  /** 订单列表(支持 platform_code/status/keyword 筛选) */
  list: (params?: {
    platform_id?: number;
    platform_code?: string;
    status?: string;
    keyword?: string;
    page?: number;
    page_size?: number;
  }) => api.get('/operate/interconnect/orders', { params }),

  get: (orderId: number) => api.get(`/operate/interconnect/orders/${orderId}`),

  /** 手动录入导流订单 */
  create: (data: Record<string, unknown>) => api.post('/operate/interconnect/orders', data),
};

/* ── 市政监管平台配置 ── */
export const supervisionAPI = {
  list: (params?: { city?: string; status?: string; page?: number; page_size?: number }) =>
    api.get('/operate/supervision/configs', { params }),

  get: (id: number) => api.get(`/operate/supervision/configs/${id}`),
  create: (data: Record<string, unknown>) => api.post('/operate/supervision/configs', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/operate/supervision/configs/${id}`, data),
  delete: (id: number) => api.delete(`/operate/supervision/configs/${id}`),
};

/* ── 监管上报记录 ── */
export const regulatoryReportAPI = {
  list: (params?: {
    config_id?: number;
    city?: string;
    report_type?: string;
    status?: string;
    page?: number;
    page_size?: number;
  }) => api.get('/operate/supervision/reports', { params }),

  get: (reportId: number) => api.get(`/operate/supervision/reports/${reportId}`),

  /** 手动触发一次上报 */
  manual: (data: { config_id: number; report_type: string; report_content?: Record<string, unknown> }) =>
    api.post('/operate/supervision/reports/manual', data),

  /** 重试失败的上报 */
  retry: (reportId: number) => api.post(`/operate/supervision/reports/${reportId}/retry`),
};

/* ── 合规检查 ── */
export const complianceAPI = {
  list: (params?: {
    config_id?: number;
    city?: string;
    check_type?: string;
    result?: string;
    page?: number;
    page_size?: number;
  }) => api.get('/operate/supervision/compliance', { params }),

  get: (checkId: number) => api.get(`/operate/supervision/compliance/${checkId}`),

  /** 触发一次合规检查 */
  run: (data: {
    config_id: number;
    check_type: string;
    result: string;
    score?: number;
    details?: Record<string, unknown>;
  }) => api.post('/operate/supervision/compliance', data),
};
