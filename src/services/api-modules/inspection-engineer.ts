/**
 * api-modules/inspection-engineer.ts — 巡检/工程师/Webhook/Fleet/Runbook API
 * 从 extended.ts 拆分 (F1361 维度22 领域细分)
 */
import api from './client';
import {
  ApiResponse,
  PaginatedData,
  InspectionPlan,
  InspectionTemplate,
  InspectionTemplateCreate,
  InspectionTemplateCreated,
  InspectionTemplateUpdate,
  InspectionTask,
  Engineer,
  Webhook,
  RunbookTemplateSummary,
  RunbookTemplateDetail,
  FleetDriver,
} from '../../types';

// =====================
// 工程师 API (/engineers)
// =====================
export interface EngineerCreate {
  username: string;
  password: string;
  name: string;
  phone?: string;
  level?: 'junior' | 'senior' | 'expert';
  role?: string;
}

export const engineerApi = {
  /** GET /engineers — 工程师列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Engineer>>> {
    return api
      .get('/engineers', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          username: (it.username as string) ?? '',
          name: (it.name as string) ?? '',
          phone: (it.phone as string | null) ?? null,
          level: (it.level as Engineer['level']) ?? 'junior',
          teamId: (it.team_id as number | null) ?? null,
          status: (it.status as Engineer['status']) ?? 'active',
          role: (it.role as string) ?? '',
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? 0,
            page: (d.page as number) ?? params?.page ?? 1,
            pageSize: (d.page_size as number) ?? params?.pageSize ?? 20,
          },
        };
      });
  },

  /** POST /engineers — 创建工程师 */
  create(body: EngineerCreate): Promise<ApiResponse<Engineer>> {
    return api
      .post('/engineers', {
        username: body.username,
        password: body.password,
        name: body.name,
        ...(body.phone !== undefined && { phone: body.phone }),
        ...(body.level !== undefined && { level: body.level }),
        ...(body.role !== undefined && { role: body.role }),
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            username: (it.username as string) ?? '',
            name: (it.name as string) ?? '',
            phone: (it.phone as string | null) ?? null,
            level: (it.level as Engineer['level']) ?? 'junior',
            teamId: (it.team_id as number | null) ?? null,
            status: (it.status as Engineer['status']) ?? 'active',
            role: (it.role as string) ?? '',
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
          },
        };
      });
  },

  /** DELETE /engineers/{id} — 删除工程师 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/engineers/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      return { ...raw, data: null };
    });
  },
};


// =====================
// Webhook API (/webhooks)
// =====================
export interface WebhookCreate {
  name: string;
  url: string;
  events?: string[];
  secret?: string;
  description?: string;
  enabled?: boolean;
}

export const webhookApi = {
  /** GET /webhooks — Webhook列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Webhook>>> {
    return api
      .get('/webhooks', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          url: (it.url as string) ?? '',
          events: ((it.event_types as string[]) ?? (it.events as string[]) ?? []),
          secret: (it.secret as string | null) ?? null,
          enabled: (it.enabled as boolean) ?? false,
          lastTriggeredAt: (it.last_triggered_at as string | null) ?? null,
          lastResponseStatus: (it.last_response_status as number | null) ?? null,
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? 0,
            page: (d.page as number) ?? params?.page ?? 1,
            pageSize: (d.page_size as number) ?? params?.pageSize ?? 20,
          },
        };
      });
  },

  /** POST /webhooks — 创建Webhook */
  create(body: WebhookCreate): Promise<ApiResponse<Webhook>> {
    return api
      .post('/webhooks', {
        name: body.name,
        url: body.url,
        events: body.events ?? [],
        ...(body.secret !== undefined && { secret: body.secret }),
        ...(body.description !== undefined && { description: body.description }),
        ...(body.enabled !== undefined && { enabled: body.enabled }),
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            url: (it.url as string) ?? '',
            events: ((it.event_types as string[]) ?? (it.events as string[]) ?? []),
            secret: (it.secret as string | null) ?? null,
            enabled: (it.enabled as boolean) ?? false,
            lastTriggeredAt: (it.last_triggered_at as string | null) ?? null,
            lastResponseStatus: (it.last_response_status as number | null) ?? null,
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
          },
        };
      });
  },

  /** DELETE /webhooks/{id} — 删除Webhook */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/webhooks/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      return { ...raw, data: null };
    });
  },
};


// =====================
// 巡检计划 API (/inspection/plans)
// =====================
export const inspectionPlanApi = {
  /** GET /inspection/plans — 巡检计划列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<InspectionPlan>>> {
    return api
      .get('/inspection/plans', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          stationId: (it.station_id as number) ?? 0,
          stationName: (it.station_name as string) ?? '',
          deviceId: it.device_id as number | undefined,
          deviceName: it.device_name as string | undefined,
          type: (it.type as InspectionPlan['type']) ?? 'daily',
          status: (it.status as InspectionPlan['status']) ?? 'pending',
          scheduledDate: (it.scheduled_date as string) ?? '',
          cycle: it.cycle as string | undefined,
          assignedTo: it.assigned_to as number | undefined,
          assignedName: it.assigned_name as string | undefined,
          templateId: it.template_id as number | undefined,
          description: it.description as string | undefined,
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? 0,
            page: (d.page as number) ?? params?.page ?? 1,
            pageSize: (d.page_size as number) ?? params?.pageSize ?? 20,
          },
        };
      });
  },
};


// =====================
// 巡检模板 API (/inspection/templates)
// =====================
export const inspectionTemplateApi = {
  /** GET /inspection/templates — 巡检模板列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<InspectionTemplate>>> {
    return api
      .get('/inspection/templates', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          type: (it.type as InspectionTemplate['type']) ?? 'daily',
          items: ((it.items as Record<string, unknown>[]) ?? []).map((item) => ({
            id: (item.id as number) ?? 0,
            name: (item.name as string) ?? '',
            expected: (item.expected as string) ?? '',
            result: item.result as 'pass' | 'fail' | 'na' | undefined,
            note: item.note as string | undefined,
          })),
          description: it.description as string | undefined,
          enabled: (it.enabled as boolean) ?? true,
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? 0,
            page: (d.page as number) ?? params?.page ?? 1,
            pageSize: (d.page_size as number) ?? params?.pageSize ?? 20,
          },
        };
      });
  },

  /** POST /inspection/templates — 创建巡检模板 */
  create(body: InspectionTemplateCreate): Promise<ApiResponse<InspectionTemplateCreated>> {
    return api
      .post('/inspection/templates', {
        name: body.name,
        ...(body.category !== undefined && { category: body.category }),
        ...(body.description !== undefined && { description: body.description }),
        ...(body.items !== undefined && { items: body.items }),
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (d.id as number) ?? 0,
            name: (d.name as string) ?? '',
            description: (d.description as string | null) ?? null,
            items: ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
              name: (it.name as string) ?? '',
              required: (it.required as boolean) ?? false,
            })),
            itemCount: (d.item_count as number) ?? 0,
            deviceTypes: (d.device_types as string[]) ?? [],
            target: (d.target as string | null) ?? null,
            status: (d.status as string) ?? 'active',
            createdAt: (d.created_at as string) ?? '',
            updatedAt: (d.updated_at as string) ?? '',
          },
        };
      });
  },

  /** PUT /inspection/templates/{id} — 更新巡检模板 */
  update(id: number, body: InspectionTemplateUpdate): Promise<ApiResponse<InspectionTemplateCreated>> {
    return api
      .put(`/inspection/templates/${id}`, {
        ...(body.name !== undefined && { name: body.name }),
        ...(body.category !== undefined && { category: body.category }),
        ...(body.description !== undefined && { description: body.description }),
        ...(body.items !== undefined && { items: body.items }),
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        if (!raw.data) return { ...raw, data: null } as unknown as ApiResponse<InspectionTemplateCreated>;
        const d = raw.data as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (d.id as number) ?? 0,
            name: (d.name as string) ?? '',
            description: (d.description as string | null) ?? null,
            items: ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
              name: (it.name as string) ?? '',
              required: (it.required as boolean) ?? false,
            })),
            itemCount: (d.item_count as number) ?? 0,
            deviceTypes: (d.device_types as string[]) ?? [],
            target: (d.target as string | null) ?? null,
            status: (d.status as string) ?? 'active',
            createdAt: (d.created_at as string) ?? '',
            updatedAt: (d.updated_at as string) ?? '',
          },
        };
      });
  },

  /** DELETE /inspection/templates/{id} — 删除巡检模板 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/inspection/templates/${id}`).then((res) => res.data);
  },
};


// =====================
// 巡检任务 V2 API (/inspection/tasks)
// =====================
export const inspectionTaskApi = {
  /** GET /inspection/tasks — 巡检任务列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<InspectionTask>>> {
    return api
      .get('/inspection/tasks', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          stationId: (it.station_id as number) ?? 0,
          stationName: (it.station_name as string) ?? '',
          deviceId: (it.device_id as number) ?? 0,
          deviceName: (it.device_name as string) ?? '',
          type: (it.type as InspectionTask['type']) ?? 'daily',
          status: (it.status as InspectionTask['status']) ?? 'pending',
          scheduledDate: (it.scheduled_date as string) ?? '',
          completedDate: it.completed_date as string | undefined,
          assignedTo: it.assigned_to as number | undefined,
          assignedName: it.assigned_name as string | undefined,
          description: (it.description as string) ?? '',
          items: ((it.items as Record<string, unknown>[]) ?? []).map((item) => ({
            id: (item.id as number) ?? 0,
            name: (item.name as string) ?? '',
            expected: (item.expected as string) ?? '',
            result: item.result as 'pass' | 'fail' | 'na' | undefined,
            note: item.note as string | undefined,
          })),
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        })) as InspectionTask[];
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? 0,
            page: (d.page as number) ?? params?.page ?? 1,
            pageSize: (d.page_size as number) ?? params?.pageSize ?? 20,
          },
        };
      });
  },
};


// =====================
// 车队 API (GET /fleet/drivers)
// =====================
export const fleetApi = {
  /** GET /fleet/drivers — 司机列表 */
  getDrivers(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<FleetDriver>>> {
    const query: Record<string, unknown> = {};
    if (params?.page) query.page = params.page;
    if (params?.pageSize) query.page_size = params.pageSize;
    return api.get('/fleet/drivers', { params: query }).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = (d.items as unknown as Record<string, unknown>[]) ?? [];
      return {
        ...raw,
        data: {
          items: items.map((item): FleetDriver => ({
            id: (item.id as number) ?? 0,
            name: (item.name as string) ?? '',
            phone: (item.phone as string) ?? null,
            licenseNumber: (item.license_number as string) ?? null,
            vehiclePlate: (item.vehicle_plate as string) ?? null,
            status: (item.status as string) ?? 'unknown',
            createdAt: (item.created_at as string) ?? null,
            updatedAt: (item.updated_at as string) ?? null,
          })),
          total: (d.total as number) ?? 0,
          page: (d.page as number) ?? 1,
          pageSize: (d.page_size as number) ?? 20,
        },
      };
    });
  },
};


// =====================
// Runbook 模板 API (GET /runbooks/templates)
// =====================
export const runbookTemplateApi = {
  /** GET /runbooks/templates — Runbook 模板列表 */
  getList(): Promise<ApiResponse<PaginatedData<RunbookTemplateSummary>>> {
    return api
      .get('/runbooks/templates')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          category: (it.category as string) ?? '',
          alarmType: (it.alarm_type as string) ?? '',
          description: (it.description as string) ?? '',
          stepCount: (it.step_count as number) ?? 0,
          autoSteps: (it.auto_steps as number) ?? 0,
          manualSteps: (it.manual_steps as number) ?? 0,
          status: (it.status as string) ?? 'active',
          version: (it.version as number) ?? 1,
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? items.length,
            page: (d.page as number) ?? 1,
            pageSize: (d.page_size as number) ?? items.length,
          },
        };
      });
  },

  /** GET /runbooks/templates/{id} — Runbook 模板详情 (含步骤) */
  getById(id: number): Promise<ApiResponse<RunbookTemplateDetail>> {
    return api
      .get(`/runbooks/templates/${id}`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        const rawSteps = (it.steps as Record<string, unknown>[]) ?? [];
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            category: (it.category as string) ?? '',
            alarmType: (it.alarm_type as string) ?? '',
            description: (it.description as string) ?? '',
            stepCount: (it.step_count as number) ?? 0,
            autoSteps: (it.auto_steps as number) ?? 0,
            manualSteps: (it.manual_steps as number) ?? 0,
            status: (it.status as string) ?? 'active',
            version: (it.version as number) ?? 1,
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
            steps: rawSteps.map((s) => ({
              stepId: (s.step_id as number) ?? 0,
              actionType: (s.action_type as string) ?? '',
              description: (s.description as string) ?? '',
              command: (s.command as string) ?? '',
              params: (s.params as Record<string, unknown>) ?? {},
              riskLevel: (s.risk_level as string) ?? 'low',
              timeoutSec: (s.timeout_sec as number) ?? 0,
              rollbackCommand: (s.rollback_command as string) ?? '',
              preCheck: (s.pre_check as string) ?? '',
              postCheck: (s.post_check as string) ?? '',
              autoExecute: (s.auto_execute as boolean) ?? false,
              status: (s.status as string) ?? 'pending',
              result: (s.result as string) ?? '',
              durationMs: (s.duration_ms as number) ?? 0,
              errorMessage: (s.error_message as string) ?? '',
            })),
          },
        };
      });
  },
};

