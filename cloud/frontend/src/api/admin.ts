/**
 * 管理后台 - 物联网接入 API 层
 *
 * 互联互通 + 市政监管已迁移至运营平台 api/operateExternal.ts
 * 本文件仅保留终端管理 + 云服务配置
 */
import api from './index';

/* ── 互联互通 + 市政监管已迁移至运营平台 (api/operateExternal.ts) ── */

/* ── 终端管理 (摄像头/传感器/门禁) ── */
export const terminalsAPI = {
  /** 终端列表(支持 terminal_type/station_name/status/keyword 筛选) */
  list: (params?: {
    terminal_type?: string;
    station_name?: string;
    status?: string;
    keyword?: string;
    page?: number;
    page_size?: number;
  }) => api.get('/admin/terminals', { params }),

  get: (id: number) => api.get(`/admin/terminals/${id}`),
  create: (data: Record<string, unknown>) => api.post('/admin/terminals', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/admin/terminals/${id}`, data),
  delete: (id: number) => api.delete(`/admin/terminals/${id}`),
};

/* ── 边缘网关 SN 平台台账 (任务卡 e940c9f4) ── */
export const edgeGatewayAPI = {
  /** 库存列表(支持 status/batch/keyword 筛选 + 分页) */
  list: (params?: {
    status?: string;
    batch?: string;
    keyword?: string;
    page?: number;
    page_size?: number;
  }) => api.get('/admin/edge-gateways', { params }),

  /** 批量生成 SN 入库 (status=inventory) */
  generate: (data: { count: number; region?: string; batch?: string }) =>
    api.post('/admin/edge-gateways/generate', data),

  /** 出库/发货 (→ shipped) */
  ship: (sn: string) => api.post(`/admin/edge-gateways/${sn}/ship`),

  /** 绑定场站 (→ bound) */
  bind: (sn: string, station_id: number) =>
    api.post(`/admin/edge-gateways/${sn}/bind`, { station_id }),

  /** 解绑 (→ inventory) */
  unbind: (sn: string) => api.post(`/admin/edge-gateways/${sn}/unbind`),

  /** 网关接入钩子 (→ online + last_online_at) */
  online: (sn: string, firmware_version?: string) =>
    api.post(`/admin/edge-gateways/${sn}/online`, { firmware_version }),

  /** 退役 (→ decommissioned) */
  decommission: (sn: string) => api.post(`/admin/edge-gateways/${sn}/decommission`),
};

/* ── 云服务配置 (公有云/私有云对接) ── */
export const cloudConfigAPI = {
  /** 云配置列表(支持 provider/sync_strategy/status/keyword 筛选) */
  list: (params?: {
    provider?: string;
    sync_strategy?: string;
    status?: string;
    keyword?: string;
    page?: number;
    page_size?: number;
  }) => api.get('/admin/cloud-configs', { params }),

  get: (id: number) => api.get(`/admin/cloud-configs/${id}`),
  create: (data: Record<string, unknown>) => api.post('/admin/cloud-configs', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/admin/cloud-configs/${id}`, data),
  delete: (id: number) => api.delete(`/admin/cloud-configs/${id}`),

  /** 连通性测试(模拟, 校验存储桶 + 同步端点可达) */
  test: (id: number) => api.post(`/admin/cloud-configs/${id}/test`),
};
