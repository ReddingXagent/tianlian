/**
 * 车队管理 - 五大模块 API 层
 *
 * 司机管理 / 碳排放 / 充电队列 / V2G调度 / 费用结算
 */
import api from './index';

/* ── 司机管理 ── */
export const fleetDriverAPI = {
  list: (params?: { enterprise_id?: number; page?: number; page_size?: number }) =>
    api.get('/fleet/drivers', { params }),
  get: (id: number) => api.get(`/fleet/drivers/${id}`),
  create: (data: Record<string, unknown>) => api.post('/fleet/drivers', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/fleet/drivers/${id}`, data),
  delete: (id: number) => api.delete(`/fleet/drivers/${id}`),
  // 账户
  getAccount: (id: number) => api.get(`/fleet/drivers/${id}/account`),
  recharge: (id: number, data: { amount: number; remark?: string }) =>
    api.post(`/fleet/drivers/${id}/account/recharge`, data),
  // 交易
  getTransactions: (id: number, params?: { page?: number; page_size?: number }) =>
    api.get(`/fleet/drivers/${id}/transactions`, { params }),
  createTransaction: (id: number, data: Record<string, unknown>) =>
    api.post(`/fleet/drivers/${id}/transactions`, data),
};

/* ── 碳排放管理 ── */
export const fleetCarbonAPI = {
  overview: (enterprise_id: number, year?: number) =>
    api.get('/fleet/carbon/overview', { params: { enterprise_id, year } }),
  details: (params: { enterprise_id: number; vehicle_id?: number; start_date?: string; end_date?: string; page?: number; page_size?: number }) =>
    api.get('/fleet/carbon/details', { params }),
  reports: (enterprise_id: number, year?: number) =>
    api.get('/fleet/carbon/reports', { params: { enterprise_id, year } }),
  verifyReport: (summary_id: number) =>
    api.post(`/fleet/carbon/reports/${summary_id}/verify`),
  // 因子
  listFactors: (params?: { year?: number; region?: string; factor_type?: string; page?: number; page_size?: number }) =>
    api.get('/fleet/carbon/factors', { params }),
  createFactor: (data: Record<string, unknown>) => api.post('/fleet/carbon/factors', data),
  updateFactor: (id: number, data: Record<string, unknown>) => api.put(`/fleet/carbon/factors/${id}`, data),
  deleteFactor: (id: number) => api.delete(`/fleet/carbon/factors/${id}`),
  // 计算
  calculate: (data: { vehicle_id: number; record_date: string; charge_energy_kwh: number }) =>
    api.post('/fleet/carbon/calculate', data),
};

/* ── 充电排序队列 ── */
export const fleetChargingQueueAPI = {
  getQueue: (station_id: number, status?: string) =>
    api.get('/fleet/charging/queue', { params: { station_id, status } }),
  enqueue: (data: Record<string, unknown>) =>
    api.post('/fleet/charging/queue/enqueue', data),
  dequeue: (queue_id: number, reason?: string) =>
    api.delete(`/fleet/charging/queue/${queue_id}/dequeue`, { params: { reason: reason || 'manual' } }),
  updatePriority: (queue_id: number, priority: number) =>
    api.patch(`/fleet/charging/queue/${queue_id}/priority`, { priority }),
  // 规则
  listRules: (enterprise_id?: number) =>
    api.get('/fleet/charging/rules', { params: { enterprise_id } }),
  createRule: (data: Record<string, unknown>) =>
    api.post('/fleet/charging/rules', data),
  updateRule: (id: number, data: Record<string, unknown>) =>
    api.put(`/fleet/charging/rules/${id}`, data),
  deleteRule: (id: number) => api.delete(`/fleet/charging/rules/${id}`),
};

/* ── V2G 车队调度 ── */
export const fleetV2GAPI = {
  // 计划
  listPlans: (params: { enterprise_id: number; vehicle_id?: number; plan_date?: string; status?: string; page?: number; page_size?: number }) =>
    api.get('/fleet/v2g/plans', { params }),
  getPlan: (id: number) => api.get(`/fleet/v2g/plans/${id}`),
  createPlan: (data: Record<string, unknown>) => api.post('/fleet/v2g/plans', data),
  updatePlanStatus: (id: number, new_status: string) =>
    api.put(`/fleet/v2g/plans/${id}/status`, null, { params: { new_status } }),
  // 收益
  listRevenue: (params: { enterprise_id: number; vehicle_id?: number; start_date?: string; end_date?: string; page?: number; page_size?: number }) =>
    api.get('/fleet/v2g/revenue', { params }),
  recordRevenue: (data: Record<string, unknown>) => api.post('/fleet/v2g/revenue', data),
  // 状态概览
  getStatus: (enterprise_id: number) => api.get('/fleet/v2g/status', { params: { enterprise_id } }),
  // 调度记录
  listRecords: (params: { enterprise_id: number; vehicle_id?: number; dispatch_type?: string; start_date?: string; end_date?: string; page?: number; page_size?: number }) =>
    api.get('/fleet/v2g/records', { params }),
};

/* ── 费用结算 ── */
export const fleetSettlementAPI = {
  // 账单
  generateBill: (data: { enterprise_id: number; bill_period: string }) =>
    api.post('/fleet/settlement/bills/generate', data),
  listBills: (params?: { enterprise_id?: number; bill_period?: string; status?: string; page?: number; page_size?: number }) =>
    api.get('/fleet/settlement/bills', { params }),
  getBill: (id: number) => api.get(`/fleet/settlement/bills/${id}`),
  confirmBill: (id: number, data?: { remark?: string }) =>
    api.post(`/fleet/settlement/bills/${id}/confirm`, data || {}),
  payBill: (id: number, data: { paid_amount: number; remark?: string }) =>
    api.post(`/fleet/settlement/bills/${id}/pay`, data),
  getBillDetails: (id: number, params?: { page?: number; page_size?: number }) =>
    api.get(`/fleet/settlement/bills/${id}/details`, { params }),
  // 发票
  requestInvoice: (bill_id: number, data: Record<string, unknown>) =>
    api.post(`/fleet/settlement/bills/${bill_id}/invoice`, data),
  listInvoices: (params?: { enterprise_id?: number; status?: string; page?: number; page_size?: number }) =>
    api.get('/fleet/settlement/invoices', { params }),
};
