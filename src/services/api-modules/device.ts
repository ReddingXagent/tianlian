/**
 * api-modules/device.ts — 设备/监控/扫码/知识库/诊断 API
 * 从 services/api.ts 拆分 (F1360 维度21 结构重构)
 */
import api from './client';
import {
  ApiResponse,
  Device,
  DeviceMetrics,
  DeviceHealth,
  DeviceHealthHistory,
  DeviceHealthSummary,
  MonitorSummary,
  ScanResult,
  PaginatedData,
  Alarm,
  ChargerConfig,
  DiagnosisResult,
  KnowledgeArticleItem,
  KnowledgeFaqItem,
  KnowledgeCategoryItem,
  KnowledgeArticleCreate,
  KnowledgeArticleCreated,
  KnowledgeArticleUpdate,
  KnowledgeArticleUpdated,
  KnowledgeCategoryCreate,
  KnowledgeCategoryCreated,
  KnowledgeCategoryUpdate,
  KnowledgeCategoryUpdated,
  KnowledgeFaqCreate,
  KnowledgeFaqCreated,
  FaqCategory,
} from '../../types';

export const deviceApi = {
  getList(params?: { stationId?: number; status?: string; page?: number; pageSize?: number }): Promise<ApiResponse<PaginatedData<Device>>> {
    return api.get('/devices', { params }).then((res) => res.data);
  },
  getDetail(id: number): Promise<ApiResponse<Device>> {
    return api.get(`/devices/${id}`).then((res) => res.data);
  },
  getMetrics(id: number): Promise<ApiResponse<DeviceMetrics>> {
    return api.get(`/devices/${id}/metrics`).then((res) => res.data);
  },
  getHealthList(params?: { status?: string; type?: string; page?: number; pageSize?: number }): Promise<ApiResponse<PaginatedData<DeviceHealthSummary>>> {
    return api.get('/devices/health', { params }).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = ((d.items as Record<string, unknown>[]) ?? []).map((item) => ({
        id: (item.id as number) ?? 0,
        code: (item.code as string) ?? '',
        name: (item.name as string) ?? '',
        type: (item.type as string) ?? '',
        healthScore: (item.health_score as number) ?? 0,
        status: (item.status as string) ?? '',
      }));
      return { ...raw, data: { items, total: (d.total as number) ?? items.length, page: (d.page as number) ?? 1, pageSize: (d.page_size as number) ?? items.length } };
    });
  },
  getHealth(id: number): Promise<ApiResponse<DeviceHealth>> {
    return api.get(`/devices/${id}/health`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return { ...raw, data: {
        deviceId: (d.device_id as number) ?? 0, deviceCode: (d.device_code as string) ?? '', deviceName: (d.device_name as string) ?? '',
        deviceType: (d.device_type as string) ?? '', healthScore: (d.health_score as number) ?? 0, healthStatus: (d.health_status as string) ?? '',
        healthStatusDisplay: (d.health_status_display as string) ?? '', dimensionScores: (d.dimension_scores as Record<string, number>) ?? {},
        checkedAt: (d.checked_at as string) ?? '', lastHealthCheck: (d.last_health_check as string | null) ?? null,
      }};
    });
  },
  getHealthHistory(id: number): Promise<ApiResponse<DeviceHealthHistory[]>> {
    return api.get(`/devices/${id}/health/history`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>[]>;
      const items = ((raw.data ?? []) as Record<string, unknown>[]).map((d) => ({
        deviceId: (d.device_id as number) ?? id, healthScore: (d.health_score as number) ?? 0,
        healthStatus: (d.health_status as string) ?? '', healthStatusDisplay: (d.health_status_display as string) ?? '',
        dimensionScores: (d.dimension_scores as Record<string, number>) ?? {}, checkedAt: (d.checked_at as string) ?? (d.created_at as string) ?? '',
      }));
      return { ...raw, data: items };
    });
  },
  getConfig(id: number): Promise<ApiResponse<ChargerConfig>> {
    return api.get(`/devices/${id}/config`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return { ...raw, data: {
        deviceId: (d.device_id as number) ?? 0, voltageLimit: (d.voltage_limit as number) ?? 0, currentLimit: (d.current_limit as number) ?? 0,
        maxPower: (d.max_power as number) ?? 0, chargeMode: (d.charge_mode as string) ?? '', overloadProtection: (d.overload_protection as boolean) ?? false,
        timePeriods: ((d.time_periods as { start_time: string; end_time: string; power_limit: number }[]) ?? []).map((tp) => ({ startTime: tp.start_time, endTime: tp.end_time, powerLimit: tp.power_limit })),
        createdAt: (d.created_at as string | null) ?? null, updatedAt: (d.updated_at as string | null) ?? null,
      }};
    });
  },
};

export const monitorApi = {
  getSummary(): Promise<ApiResponse<MonitorSummary>> { return api.get('/monitor/summary').then((res) => res.data); },
  getFaultDevices(params?: { page?: number; pageSize?: number }): Promise<ApiResponse<PaginatedData<Device>>> { return api.get('/monitor/faults', { params }).then((res) => res.data); },
  getCriticalAlarms(params?: { page?: number; pageSize?: number }): Promise<ApiResponse<PaginatedData<Alarm>>> { return api.get('/monitor/critical-alarms', { params }).then((res) => res.data); },
};

export const scanApi = {
  scan(code: string): Promise<ApiResponse<ScanResult>> { return api.post('/scan', { code }).then((res) => res.data); },
  scanDevice(deviceCode: string): Promise<ApiResponse<Device>> { return api.post('/scan/device', { code: deviceCode }).then((res) => res.data); },
  checkIn(deviceId: number, location?: { lat: number; lng: number }): Promise<ApiResponse<{ success: boolean; message: string }>> { return api.post('/scan/check-in', { deviceId, location }).then((res) => res.data); },
};

export const knowledgeApi = {
  getArticles(params?: { page?: number; page_size?: number }): Promise<ApiResponse<PaginatedData<KnowledgeArticleItem>>> {
    const query = params ? `?page=${params.page ?? 1}&page_size=${params.page_size ?? 20}` : '';
    return api.get(`/knowledge/articles${query}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
        id: (it.id as number) ?? 0, title: (it.title as string) ?? '', content: (it.content as string) ?? '',
        summary: (it.summary as string) ?? '', categoryId: (it.category_id as number) ?? 0, categoryName: (it.category_name as string) ?? undefined,
        tags: ((it.tags as string[]) ?? []), author: (it.author as string) ?? '', viewCount: (it.view_count as number) ?? 0,
        status: (it.status as 'published' | 'draft' | 'archived') ?? 'draft', createdAt: (it.created_at as string) ?? '', updatedAt: (it.updated_at as string) ?? '',
      }));
      return { ...raw, data: { items, total: (d.total as number) ?? 0, page: (d.page as number) ?? 1, pageSize: (d.page_size as number) ?? 20 } };
    });
  },
  getFaq(): Promise<ApiResponse<KnowledgeFaqItem[]>> {
    return api.get('/knowledge/faq').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>[] | Record<string, unknown>>;
      const items = (Array.isArray(raw.data) ? raw.data : (raw.data as Record<string, unknown>)?.items ?? []) as Record<string, unknown>[];
      const mapped = items.map((it) => ({ id: (it.id as number) ?? 0, question: (it.question as string) ?? '', answer: (it.answer as string) ?? '', categoryId: (it.category_id as number) ?? undefined, sortOrder: (it.sort_order as number) ?? undefined }));
      return { ...raw, data: mapped };
    });
  },
  getFaqCategories(): Promise<ApiResponse<FaqCategory[]>> {
    return api.get('/knowledge/faq/categories').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>[] | Record<string, unknown>>;
      const items = (Array.isArray(raw.data) ? raw.data : (raw.data as Record<string, unknown>)?.items ?? []) as Record<string, unknown>[];
      const mapped = items.map((it) => ({ id: (it.id as number) ?? 0, name: (it.name as string) ?? '', description: (it.description as string) ?? undefined, faqCount: (it.faq_count as number) ?? undefined, sortOrder: (it.sort_order as number) ?? undefined }));
      return { ...raw, data: mapped };
    });
  },
  getCategories(): Promise<ApiResponse<KnowledgeCategoryItem[]>> {
    return api.get('/knowledge/categories').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>[] | Record<string, unknown>>;
      const items = (Array.isArray(raw.data) ? raw.data : (raw.data as Record<string, unknown>)?.items ?? []) as Record<string, unknown>[];
      const mapped = items.map((it) => ({ id: (it.id as number) ?? 0, name: (it.name as string) ?? '', description: (it.description as string) ?? '', articleCount: (it.article_count as number) ?? 0, createdAt: (it.created_at as string) ?? '', updatedAt: (it.updated_at as string) ?? '' }));
      return { ...raw, data: mapped };
    });
  },
  search(keyword: string, params?: { page?: number; page_size?: number }): Promise<ApiResponse<PaginatedData<KnowledgeArticleItem>>> {
    const page = params?.page ?? 1; const pageSize = params?.page_size ?? 20;
    return api.get(`/knowledge/search?q=${encodeURIComponent(keyword)}&page=${page}&page_size=${pageSize}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
        id: (it.id as number) ?? 0, title: (it.title as string) ?? '', content: (it.content as string) ?? '', summary: (it.summary as string) ?? '',
        categoryId: (it.category_id as number) ?? 0, categoryName: (it.category_name as string) ?? undefined, tags: ((it.tags as string[]) ?? []),
        author: (it.author as string) ?? '', viewCount: (it.view_count as number) ?? 0, status: (it.status as 'published' | 'draft' | 'archived') ?? 'draft',
        createdAt: (it.created_at as string) ?? '', updatedAt: (it.updated_at as string) ?? '',
      }));
      return { ...raw, data: { items, total: (d.total as number) ?? 0, page: (d.page as number) ?? 1, pageSize: (d.page_size as number) ?? 20 } };
    });
  },
  createArticle(body: KnowledgeArticleCreate): Promise<ApiResponse<KnowledgeArticleCreated>> {
    const payload: Record<string, unknown> = { title: body.title, content: body.content };
    if (body.categoryId !== undefined) payload.category_id = body.categoryId;
    if (body.tags !== undefined) payload.tags = body.tags;
    return api.post('/knowledge/articles', payload).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const it = (raw.data ?? {}) as Record<string, unknown>;
      return { ...raw, data: { id: (it.id as number) ?? 0, title: (it.title as string) ?? '', content: (it.content as string) ?? '', category: (it.category as string) ?? '', tags: (it.tags as string[] | null) ?? null, viewCount: (it.view_count as number) ?? 0, published: (it.published as boolean) ?? false, createdAt: (it.created_at as string) ?? '', authorId: (it.author_id as number) ?? 0 } };
    });
  },
  updateArticle(id: number, body: KnowledgeArticleUpdate): Promise<ApiResponse<KnowledgeArticleUpdated>> {
    const payload: Record<string, unknown> = {};
    if (body.title !== undefined) payload.title = body.title;
    if (body.content !== undefined) payload.content = body.content;
    if (body.categoryId !== undefined) payload.category_id = body.categoryId;
    if (body.tags !== undefined) payload.tags = body.tags;
    return api.put(`/knowledge/articles/${id}`, payload).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const it = (raw.data ?? {}) as Record<string, unknown>;
      return { ...raw, data: { id: (it.id as number) ?? 0, title: (it.title as string) ?? '', content: (it.content as string) ?? '', category: (it.category as string) ?? '', tags: (it.tags as string[] | null) ?? null, viewCount: (it.view_count as number) ?? 0, published: (it.published as boolean) ?? false, updatedAt: (it.updated_at as string) ?? '', authorId: (it.author_id as number) ?? 0 } };
    });
  },
  createCategory(body: KnowledgeCategoryCreate): Promise<ApiResponse<KnowledgeCategoryCreated>> {
    const params: Record<string, unknown> = { name: body.name };
    if (body.sortOrder !== undefined) params.sort_order = body.sortOrder;
    if (body.description !== undefined) params.description = body.description;
    return api.post('/knowledge/categories', {}, { params }).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const it = (raw.data ?? {}) as Record<string, unknown>;
      return { ...raw, data: { id: (it.id as number) ?? 0, name: (it.name as string) ?? '', icon: (it.icon as string) ?? '', sortOrder: (it.sort_order as number) ?? 0, description: (it.description as string) ?? '', createdAt: (it.created_at as string) ?? '' } };
    });
  },
  updateCategory(id: number, body: KnowledgeCategoryUpdate): Promise<ApiResponse<KnowledgeCategoryUpdated>> {
    const payload: Record<string, unknown> = {};
    if (body.name !== undefined) payload.name = body.name;
    if (body.sortOrder !== undefined) payload.sort_order = body.sortOrder;
    if (body.description !== undefined) payload.description = body.description;
    return api.put(`/knowledge/categories/${id}`, payload).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const it = (raw.data ?? {}) as Record<string, unknown>;
      return { ...raw, data: { id: (it.id as number) ?? 0, name: (it.name as string) ?? '', icon: (it.icon as string) ?? '', sortOrder: (it.sort_order as number) ?? 0, description: (it.description as string) ?? '', createdAt: (it.created_at as string) ?? '', updatedAt: (it.updated_at as string | null) ?? null } };
    });
  },
  createFaq(body: KnowledgeFaqCreate): Promise<ApiResponse<KnowledgeFaqCreated>> {
    const payload: Record<string, unknown> = { question: body.question, answer: body.answer, category: body.category };
    if (body.tags !== undefined) payload.tags = body.tags;
    return api.post('/knowledge/faq', payload).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const it = (raw.data ?? {}) as Record<string, unknown>;
      return { ...raw, data: { id: (it.id as number) ?? 0, question: (it.question as string) ?? '', answer: (it.answer as string) ?? '', category: (it.category as string) ?? '', tags: (it.tags as string[] | null) ?? null, views: (it.views as number) ?? 0, helpfulCount: (it.helpful_count as number) ?? 0, createdAt: (it.created_at as string) ?? '' } };
    });
  },
  deleteCategory(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/knowledge/categories/${id}`).then((res) => res.data);
  },
};

export const diagnosisApi = {
  getDiagnosis(faultCode: string): Promise<ApiResponse<DiagnosisResult>> {
    return api.get('/diagnosis', { params: { code: faultCode } }).then((res) => res.data);
  },
};
