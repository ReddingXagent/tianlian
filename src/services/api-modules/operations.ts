/**
 * api-modules/operations.ts — 工单记录/操作/转派/设备监控/巡检/看板/角色/权限
 * 从 services/api.ts 拆分 (F1360 维度21 结构重构)
 */
import api from './client';
import {
  ApiResponse,
  WorkOrderRecord,
  WorkOrderRating,
  WorkOrderSparePartCreate,
  WorkOrderSparePartCreated,
  DeviceMetrics,
  RealtimeOverview,
  Device,
  PaginatedData,
  InspectionTask,
  DashboardData,
  AlarmTrend,
  WorkOrderTrend,
  DeviceHealthStats,
  Role,
  RoleUpdate,
  RoleCreate,
  Permission,
  PermissionTreeNode,
} from '../../types';

interface RawRecord {
  id?: string | number;
  action?: string;
  description?: string;
  created_at?: string;
}

export const workOrderRecordApi = {
  getRecords(orderId: string): Promise<ApiResponse<WorkOrderRecord[]>> {
    return api.get(`/work-orders/${orderId}/logs`).then((res) => {
      const env = res.data as ApiResponse<Record<string, unknown>>;
      const items = ((env.data as Record<string, unknown>)?.items as RawRecord[]) ?? [];
      return {
        ...env,
        data: items.map((it) => ({
          id: Number(it.id ?? 0),
          orderId,
          action: (it.action ?? 'executing') as WorkOrderRecord['action'],
          operatorId: 0,
          operatorName: '系统',
          note: it.description ?? '',
          createdAt: it.created_at ?? '',
        })),
      };
    });
  },
  /** @cloud-down 2026-08-18 F1392: POST /work-orders/{id}/notes → 404 (still down since F1368, never revived (6th round)) */
  addRecord(orderId: string, data: { action: string; note: string }): Promise<ApiResponse<WorkOrderRecord>> {
    return api.post(`/work-orders/${orderId}/notes`, data).then((res) => {
      const env = res.data as ApiResponse<Record<string, unknown>>;
      const it = (env.data ?? {}) as Record<string, unknown>;
      return {
        ...env,
        data: {
          id: Number(it.id ?? 0),
          orderId,
          action: (String(it.action ?? data.action)) as WorkOrderRecord['action'],
          operatorId: 0,
          operatorName: '手工记录',
          note: String(it.description ?? data.note),
          createdAt: String(it.created_at ?? ''),
        },
      };
    });
  },
};

export const workOrderActionApi = {
  /** @cloud-down 2026-08-18 F1392: POST /work-orders/{id}/accept → 404 (was 400 in F1389; 6th round down (flip pattern broken): F1368↓ F1384↑ F1388↓ F1389↑ F1390↓ F1391↓ F1392↓) */
  accept(id: string): Promise<ApiResponse<unknown>> {
    return api.post(`/work-orders/${id}/accept`).then((res) => res.data);
  },
  /** @cloud-down 2026-08-18 F1392: POST /work-orders/{id}/start → 404 (was 400 in F1389; 6th round down (flip pattern broken): F1368↓ F1384↑ F1388↓ F1389↑ F1390↓ F1391↓ F1392↓) */
  start(id: string): Promise<ApiResponse<unknown>> {
    return api.post(`/work-orders/${id}/start`).then((res) => res.data);
  },
  /** @cloud-down 2026-08-18 F1392: POST /work-orders/{id}/complete → 404 (was 400 in F1389; 6th round down (flip pattern broken): F1368↓ F1384↑ F1388↓ F1389↑ F1390↓ F1391↓ F1392↓) */
  complete(id: string, solution?: string): Promise<ApiResponse<unknown>> {
    return api
      .post(`/work-orders/${id}/complete`, null, { params: solution ? { solution } : {} })
      .then((res) => res.data);
  },
  /** @cloud-down 2026-08-18 F1392: POST /work-orders/{id}/verify → 404 (was 400 in F1389; 6th round down (flip pattern broken): F1368↓ F1384↑ F1388↓ F1389↑ F1390↓ F1391↓ F1392↓) */
  verify(id: string): Promise<ApiResponse<unknown>> {
    return api.post(`/work-orders/${id}/verify`).then((res) => res.data);
  },
  transfer(
    id: string,
    targetEngineerId: number,
    reason: string,
  ): Promise<ApiResponse<null>> {
    return api
      .post(`/work-orders/${id}/transfer`, {
        target_engineer_id: targetEngineerId,
        reason,
      })
      .then((res) => res.data);
  },
  reject(id: string, reason: string): Promise<ApiResponse<null>> {
    return api
      .post(`/work-orders/${id}/reject`, null, { params: { reason } })
      .then((res) => res.data);
  },
  rate(id: string, rating: WorkOrderRating): Promise<ApiResponse<null>> {
    return api
      .post(`/work-orders/${id}/rate`, {
        response_rating: rating.responseRating,
        quality_rating: rating.qualityRating,
        attitude_rating: rating.attitudeRating,
        ...(rating.comment !== undefined ? { comment: rating.comment } : {}),
      })
      .then((res) => res.data);
  },
  requestSparePart(
    id: string,
    body: WorkOrderSparePartCreate,
  ): Promise<ApiResponse<WorkOrderSparePartCreated>> {
    return api
      .post(`/work-orders/${id}/spare-parts`, {
        part_name: body.partName,
        reason: body.reason,
        ...(body.partModel !== undefined ? { part_model: body.partModel } : {}),
        ...(body.quantity !== undefined ? { quantity: body.quantity } : {}),
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        if (!raw.data) return { ...raw, data: null } as unknown as ApiResponse<WorkOrderSparePartCreated>;
        const d = raw.data as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (d.id as number) ?? 0,
            orderId: (d.order_id as string) ?? '',
            partName: (d.part_name as string) ?? '',
            partModel: (d.part_model as string | null) ?? null,
            quantity: (d.quantity as number) ?? 1,
            reason: (d.reason as string) ?? '',
            status: (d.status as string) ?? 'requested',
            inventoryDeducted: (d.inventory_deducted as boolean) ?? false,
            createdAt: (d.created_at as string) ?? '',
          } as WorkOrderSparePartCreated,
        };
      });
  },
};

export const deviceMonitorApi = {
  getRealtimeOverview(): Promise<ApiResponse<RealtimeOverview>> {
    return api.get('/monitor/realtime').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          totalPower: (d.totalPower as number) ?? 0,
          powerTrend: (d.powerTrend as number) ?? 0,
          todayGeneration: (d.todayGeneration as number) ?? 0,
          todayConsumption: (d.todayConsumption as number) ?? 0,
          gridImport: (d.gridImport as number) ?? 0,
          gridExport: (d.gridExport as number) ?? 0,
          efficiency: (d.efficiency as number) ?? 0,
          updateTime: (d.update_time as string) ?? '',
          devices: ((d.devices as Record<string, unknown>[]) ?? []).map((it) => ({
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            type: (it.type as string) ?? '',
            power: (it.power as number) ?? 0,
            status: (it.status as string) ?? '',
          })),
        } as RealtimeOverview,
      };
    });
  },
  /** @deprecated Use getRealtimeOverview() instead */
  getRealtimeMetrics(_deviceIds?: number[]): Promise<ApiResponse<DeviceMetrics[]>> {
    return Promise.resolve({ code: 200, message: 'deprecated', data: [] });
  },
  getDeviceStatusList(params?: {
    status?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Device>>> {
    return api.get('/monitor/devices', { params }).then((res) => res.data);
  },
};

export const inspectionApi = {
  getList(params?: {
    stationId?: number;
    status?: string;
    type?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<InspectionTask>>> {
    return api.get('/inspections', { params }).then((res) => res.data);
  },
  getDetail(id: number): Promise<ApiResponse<InspectionTask>> {
    return api.get(`/inspections/${id}`).then((res) => res.data);
  },
  create(data: Partial<InspectionTask>): Promise<ApiResponse<InspectionTask>> {
    return api.post('/inspections', data).then((res) => res.data);
  },
  start(id: number): Promise<ApiResponse<InspectionTask>> {
    return api.post(`/inspections/${id}/start`).then((res) => res.data);
  },
  updateItem(
    taskId: number,
    itemId: number,
    data: { result: string; note?: string }
  ): Promise<ApiResponse<InspectionTask>> {
    return api.patch(`/inspections/${taskId}/items/${itemId}`, data).then((res) => res.data);
  },
  complete(id: number, data: { summary: string; overall: string }): Promise<ApiResponse<InspectionTask>> {
    return api.post(`/inspections/${id}/complete`, data).then((res) => res.data);
  },
};

export const dashboardApi = {
  getDashboard(): Promise<ApiResponse<DashboardData>> {
    return api.get('/dashboard').then((res) => res.data);
  },
  getAlarmTrends(params?: { days?: number }): Promise<ApiResponse<AlarmTrend[]>> {
    return api.get('/dashboard/alarm-trends', { params }).then((res) => res.data);
  },
  getWorkOrderTrends(params?: { days?: number }): Promise<ApiResponse<WorkOrderTrend[]>> {
    return api.get('/dashboard/workorder-trends', { params }).then((res) => res.data);
  },
  getDeviceHealth(): Promise<ApiResponse<DeviceHealthStats>> {
    return api.get('/dashboard/device-health').then((res) => res.data);
  },
};

export const workOrderTransferApi = {
  transfer(id: string, data: { targetEngineerId: number; reason: string }): Promise<ApiResponse<unknown>> {
    return api
      .post(`/work-orders/${id}/transfer`, {
        target_engineer_id: data.targetEngineerId,
        reason: data.reason,
      })
      .then((res) => res.data);
  },
  /** @cloud-down 2026-08-18 F1392: POST /work-orders/{id}/urge → 404 (was 400 in F1389; 6th round down (flip pattern broken): F1368↓ F1384↑ F1388↓ F1389↑ F1390↓ F1391↓ F1392↓) */
  urge(id: string, message = '请尽快处理'): Promise<ApiResponse<unknown>> {
    return api.post(`/work-orders/${id}/urge`, { message }).then((res) => res.data);
  },
};

export const roleApi = {
  getList(): Promise<ApiResponse<Role[]>> {
    return api.get('/roles').then((res) => {
      const raw = res.data as ApiResponse<{ items?: Record<string, unknown>[] }>;
      const items = (raw.data?.items ?? []) as Record<string, unknown>[];
      return {
        ...raw,
        data: items.map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          displayName: (it.display_name as string) ?? '',
          description: (it.description as string) ?? '',
          isSystem: (it.is_system as boolean) ?? false,
          permissions: (it.permissions as string[]) ?? [],
        })),
      };
    });
  },
  getById(id: number): Promise<ApiResponse<Role>> {
    return api.get(`/roles/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const it = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          displayName: (it.display_name as string) ?? '',
          description: (it.description as string) ?? '',
          isSystem: (it.is_system as boolean) ?? false,
          permissions: (it.permissions as string[]) ?? [],
        },
      };
    });
  },
  update(id: number, body: RoleUpdate): Promise<ApiResponse<Role>> {
    const payload: Record<string, unknown> = {};
    if (body.displayName !== undefined) payload.display_name = body.displayName;
    if (body.description !== undefined) payload.description = body.description;
    if (body.permissions !== undefined) payload.permissions = body.permissions;
    return api.put(`/roles/${id}`, payload).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const it = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          displayName: (it.display_name as string) ?? '',
          description: (it.description as string) ?? '',
          isSystem: (it.is_system as boolean) ?? false,
          permissions: (it.permissions as string[]) ?? [],
        },
      };
    });
  },
  create(body: RoleCreate): Promise<ApiResponse<Role>> {
    const payload: Record<string, unknown> = { name: body.name };
    if (body.displayName !== undefined) payload.display_name = body.displayName;
    if (body.description !== undefined) payload.description = body.description;
    if (body.permissions !== undefined) payload.permissions = body.permissions;
    return api.post('/roles', payload).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const it = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          displayName: (it.display_name as string) ?? '',
          description: (it.description as string) ?? '',
          isSystem: (it.is_system as boolean) ?? false,
          permissions: (it.permissions as string[]) ?? [],
        },
      };
    });
  },
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/roles/${id}`).then((res) => {
      const raw = res.data as ApiResponse<null>;
      return { ...raw, data: null };
    });
  },
  getTree(): Promise<ApiResponse<PermissionTreeNode[]>> {
    return api.get('/roles/tree').then((res) => {
      const raw = res.data as ApiResponse<{ tree?: Record<string, unknown>[] }>;
      const items = (raw.data?.tree ?? []) as Record<string, unknown>[];
      const mapNode = (it: Record<string, unknown>): PermissionTreeNode => ({
        key: (it.key as string) ?? '',
        title: (it.title as string) ?? '',
        resource: (it.resource as string) ?? '',
        name: it.name as string | undefined,
        action: it.action as string | undefined,
        label: it.label as string | undefined,
        isLeaf: (it.is_leaf as boolean) ?? false,
        children: Array.isArray(it.children)
          ? (it.children as Record<string, unknown>[]).map(mapNode)
          : undefined,
      });
      return { ...raw, data: items.map(mapNode) };
    });
  },
};

export const permissionApi = {
  getList(): Promise<ApiResponse<Permission[]>> {
    return api.get('/permissions').then((res) => {
      const raw = res.data as ApiResponse<{ items?: Record<string, unknown>[] }>;
      const items = (raw.data?.items ?? []) as Record<string, unknown>[];
      return {
        ...raw,
        data: items.map((it) => ({
          name: (it.name as string) ?? '',
          resource: (it.resource as string) ?? '',
          action: (it.action as string) ?? '',
          label: (it.label as string) ?? '',
          labelShort: (it.label_short as string) ?? '',
        })),
      };
    });
  },
};
