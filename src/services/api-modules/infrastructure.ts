/**
 * api-modules/infrastructure.ts — 设施/充电/网关/VPP/健康/缓存 API
 * 从 extended.ts 拆分 (F1361 维度22 领域细分)
 */
import api, { type HealthInfo } from './client';
import {
  ApiResponse,
  PaginatedData,
  SparePart,
  SparePartCreate,
  ChargingOrder,
  PricingRule,
  DeviceHealthRanking,
  Gateway,
  GatewayStatus,
  GatewayFirmware,
  VppResource,
  VppResourceType,
  VppDispatchMode,
  VppDispatchCommand,
  VppDispatchPlan,
  VppDispatchHistory,
  ChatSource,
  ChatAction,
  ChatResponse,
  HealthStatus,
  SystemHealth,
  LivenessProbe,
  CacheStats,
} from '../../types';

// =====================
// 备件 API (GET /spare-parts)
// =====================
export const sparePartApi = {
  /** GET /spare-parts — 备件列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<SparePart>>> {
    return api
      .get('/spare-parts', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          partName: (it.part_name as string) ?? '',
          partModel: (it.part_model as string | null) ?? null,
          totalQuantity: (it.total_quantity as number) ?? 0,
          availableQuantity: (it.available_quantity as number) ?? 0,
          warehouse: (it.warehouse as string) ?? '',
          createdAt: (it.created_at as string) ?? '',
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

  /** GET /spare-parts/{id} — 备件详情 */
  getById(id: number): Promise<ApiResponse<SparePart>> {
    return api.get(`/spare-parts/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          id: (d.id as number) ?? 0,
          partName: (d.part_name as string) ?? '',
          partModel: (d.part_model as string | null) ?? null,
          totalQuantity: (d.total_quantity as number) ?? 0,
          availableQuantity: (d.available_quantity as number) ?? 0,
          warehouse: (d.warehouse as string) ?? '',
          createdAt: (d.created_at as string) ?? '',
        },
      };
    });
  },

  /** POST /spare-parts — 创建备件 (登记入库) */
  create(body: SparePartCreate): Promise<ApiResponse<SparePart>> {
    return api.post('/spare-parts', body).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          id: (d.id as number) ?? 0,
          partName: (d.part_name as string) ?? '',
          partModel: (d.part_model as string | null) ?? null,
          totalQuantity: (d.total_quantity as number) ?? 0,
          availableQuantity: (d.available_quantity as number) ?? 0,
          warehouse: (d.warehouse as string) ?? '',
          createdAt: (d.created_at as string) ?? '',
        },
      };
    });
  },

  /** DELETE /spare-parts/{id} — 删除备件 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/spare-parts/${id}`).then((res) => res.data);
  },
};


// =====================
// 充电订单 API (/charging-orders)
// =====================
export const chargingOrderApi = {
  /** GET /charging-orders — 充电订单列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
    stationId?: number;
    orderStatus?: string;
    paymentStatus?: string;
  }): Promise<ApiResponse<PaginatedData<ChargingOrder>>> {
    return api
      .get('/charging-orders', {
        params: {
          page: params?.page,
          page_size: params?.pageSize,
          station_id: params?.stationId,
          order_status: params?.orderStatus,
          payment_status: params?.paymentStatus,
        },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          orderNo: (it.order_no as string) ?? '',
          stationId: (it.station_id as number) ?? 0,
          deviceId: (it.device_id as number) ?? 0,
          userId: (it.user_id as number) ?? 0,
          userType: (it.user_type as string | null) ?? null,
          vehicleId: (it.vehicle_id as string | null) ?? null,
          plateNumber: (it.plate_number as string | null) ?? null,
          startTime: (it.start_time as string | null) ?? null,
          endTime: (it.end_time as string | null) ?? null,
          durationMinutes: (it.duration_minutes as number) ?? 0,
          startSoc: it.start_soc as number | null ?? null,
          endSoc: it.end_soc as number | null ?? null,
          startMeter: it.start_meter as number | null ?? null,
          endMeter: it.end_meter as number | null ?? null,
          stopReason: (it.stop_reason as string | null) ?? null,
          chargedKwh: (it.charged_kwh as number) ?? 0,
          electricityFee: (it.electricity_fee as number) ?? 0,
          serviceFee: (it.service_fee as number) ?? 0,
          parkingFee: (it.parking_fee as number) ?? 0,
          idlePenalty: (it.idle_penalty as number) ?? 0,
          reservationFee: (it.reservation_fee as number) ?? 0,
          totalAmount: (it.total_amount as number) ?? 0,
          discountAmount: (it.discount_amount as number) ?? 0,
          paidAmount: (it.paid_amount as number) ?? 0,
          paymentStatus: (it.payment_status as ChargingOrder['paymentStatus']) ?? 'unpaid',
          orderStatus: (it.order_status as ChargingOrder['orderStatus']) ?? 'pending',
          paymentMethod: (it.payment_method as string | null) ?? null,
          remark: (it.remark as string | null) ?? null,
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

  /** GET /charging-orders/{id} — 充电订单详情 */
  getById(id: number): Promise<ApiResponse<ChargingOrder | null>> {
    return api.get(`/charging-orders/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown> | null>;
      const it = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: raw.data
          ? {
              id: (it.id as number) ?? 0,
              orderNo: (it.order_no as string) ?? '',
              stationId: (it.station_id as number) ?? 0,
              deviceId: (it.device_id as number) ?? 0,
              userId: (it.user_id as number) ?? 0,
              userType: (it.user_type as string | null) ?? null,
              vehicleId: (it.vehicle_id as string | null) ?? null,
              plateNumber: (it.plate_number as string | null) ?? null,
              startTime: (it.start_time as string | null) ?? null,
              endTime: (it.end_time as string | null) ?? null,
              durationMinutes: (it.duration_minutes as number) ?? 0,
              startSoc: it.start_soc as number | null ?? null,
              endSoc: it.end_soc as number | null ?? null,
              startMeter: it.start_meter as number | null ?? null,
              endMeter: it.end_meter as number | null ?? null,
              stopReason: (it.stop_reason as string | null) ?? null,
              chargedKwh: (it.charged_kwh as number) ?? 0,
              electricityFee: (it.electricity_fee as number) ?? 0,
              serviceFee: (it.service_fee as number) ?? 0,
              parkingFee: (it.parking_fee as number) ?? 0,
              idlePenalty: (it.idle_penalty as number) ?? 0,
              reservationFee: (it.reservation_fee as number) ?? 0,
              totalAmount: (it.total_amount as number) ?? 0,
              discountAmount: (it.discount_amount as number) ?? 0,
              paidAmount: (it.paid_amount as number) ?? 0,
              paymentStatus: (it.payment_status as ChargingOrder['paymentStatus']) ?? 'unpaid',
              orderStatus: (it.order_status as ChargingOrder['orderStatus']) ?? 'pending',
              paymentMethod: (it.payment_method as string | null) ?? null,
              remark: (it.remark as string | null) ?? null,
              createdAt: (it.created_at as string) ?? '',
              updatedAt: (it.updated_at as string) ?? '',
            }
          : null,
      };
    });
  },
};


// =====================
// 定价规则 API (/pricing)
// =====================
export const pricingApi = {
  /** GET /pricing — 定价规则列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<PricingRule>>> {
    return api
      .get('/pricing', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          periodType: (it.period_type as string) ?? '',
          startTime: (it.start_time as string) ?? '',
          endTime: (it.end_time as string) ?? '',
          energyPrice: it.energy_price as number | undefined,
          servicePrice: it.service_price as number | undefined,
          powerLimit: it.power_limit as number | undefined,
          enabled: (it.enabled as boolean) ?? false,
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

  /** GET /pricing/{id} — 定价规则详情 */
  getById(id: number): Promise<ApiResponse<PricingRule | null>> {
    return api.get(`/pricing/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown> | null>;
      const it = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: raw.data
          ? {
              id: (it.id as number) ?? 0,
              name: (it.name as string) ?? '',
              periodType: (it.period_type as string) ?? '',
              startTime: (it.start_time as string) ?? '',
              endTime: (it.end_time as string) ?? '',
              energyPrice: it.energy_price as number | undefined,
              servicePrice: it.service_price as number | undefined,
              powerLimit: it.power_limit as number | undefined,
              enabled: (it.enabled as boolean) ?? false,
              createdAt: (it.created_at as string) ?? '',
              updatedAt: (it.updated_at as string) ?? '',
            }
          : null,
      };
    });
  },
};


export const deviceHealthApi = {
  /** GET /health/devices — 设备健康度排名 */
  getRanking(): Promise<ApiResponse<DeviceHealthRanking>> {
    return api.get('/health/devices').then((res) => res.data as ApiResponse<DeviceHealthRanking>);
  },
};


// =====================
// 网关管理 API (/gateways)
// =====================
export interface GatewayCreate {
  sn: string;
  name: string;
  stationId?: number;
  model?: string;
  manufacturer?: string;
}

export const gatewayApi = {
  /** GET /gateways — 网关列表 */
  getList(): Promise<ApiResponse<PaginatedData<Gateway>>> {
    return api.get('/gateways').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = (d.items as Record<string, unknown>[]) ?? [];
      return {
        ...raw,
        data: {
          items: items.map((item): Gateway => ({
            id: item.id as number,
            sn: (item.sn as string) ?? '',
            name: (item.name as string) ?? '',
            model: (item.model as string) ?? null,
            manufacturer: (item.manufacturer as string) ?? null,
            stationId: (item.station_id as number) ?? null,
            status: (item.status as Gateway['status']) ?? 'offline',
            firmwareVersion: (item.firmware_version as string) ?? null,
            lastOnline: (item.last_online as string) ?? null,
            ipAddress: (item.ip_address as string) ?? null,
            macAddress: (item.mac_address as string) ?? null,
            location: (item.location as string) ?? null,
            healthScore: (item.health_score as number) ?? 0,
            createdAt: (item.created_at as string) ?? '',
            updatedAt: (item.updated_at as string) ?? '',
            notes: (item.notes as string) ?? null,
          })),
          total: (d.total as number) ?? 0,
          page: (d.page as number) ?? 1,
          pageSize: (d.page_size as number) ?? 20,
        },
      };
    });
  },

  /** GET /gateways/{id} — 网关详情 */
  getById(id: number): Promise<ApiResponse<Gateway>> {
    return api.get(`/gateways/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const item = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          id: item.id as number,
          sn: (item.sn as string) ?? '',
          name: (item.name as string) ?? '',
          model: (item.model as string) ?? null,
          manufacturer: (item.manufacturer as string) ?? null,
          stationId: (item.station_id as number) ?? null,
          status: (item.status as Gateway['status']) ?? 'offline',
          firmwareVersion: (item.firmware_version as string) ?? null,
          lastOnline: (item.last_online as string) ?? null,
          ipAddress: (item.ip_address as string) ?? null,
          macAddress: (item.mac_address as string) ?? null,
          location: (item.location as string) ?? null,
          healthScore: (item.health_score as number) ?? 0,
          createdAt: (item.created_at as string) ?? '',
          updatedAt: (item.updated_at as string) ?? '',
          notes: (item.notes as string) ?? null,
        },
      };
    });
  },

  /** GET /gateways/firmware — 固件包列表 */
  getFirmware(): Promise<ApiResponse<PaginatedData<GatewayFirmware>>> {
    return api.get('/gateways/firmware').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = (d.items as Record<string, unknown>[]) ?? [];
      return {
        ...raw,
        data: {
          items: items.map((item): GatewayFirmware => ({
            id: item.id as number,
            version: (item.version as string) ?? '',
            fileId: (item.file_id as string) ?? null,
            fileSize: (item.file_size as number) ?? null,
            releaseNotes: (item.release_notes as string) ?? null,
            status: (item.status as string) ?? null,
            createdAt: (item.created_at as string) ?? '',
            updatedAt: (item.updated_at as string) ?? null,
          })),
          total: (d.total as number) ?? 0,
          page: (d.page as number) ?? 1,
          pageSize: (d.page_size as number) ?? 20,
        },
      };
    });
  },

  /** GET /gateways/status — 网关状态统计 */
  getStatus(): Promise<ApiResponse<GatewayStatus>> {
    return api.get('/gateways/status').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          onlineCount: (d.online_count as number) ?? 0,
          offlineCount: (d.offline_count as number) ?? 0,
          maintenanceCount: (d.maintenance_count as number) ?? 0,
          faultCount: (d.fault_count as number) ?? 0,
          total: (d.total as number) ?? 0,
        },
      };
    });
  },

  /** POST /gateways — 创建网关 */
  create(body: GatewayCreate): Promise<ApiResponse<Gateway>> {
    return api
      .post('/gateways', {
        sn: body.sn,
        name: body.name,
        ...(body.stationId !== undefined && { station_id: body.stationId }),
        ...(body.model !== undefined && { model: body.model }),
        ...(body.manufacturer !== undefined && { manufacturer: body.manufacturer }),
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            sn: (it.sn as string) ?? '',
            name: (it.name as string) ?? '',
            model: (it.model as string) ?? null,
            manufacturer: (it.manufacturer as string) ?? null,
            stationId: (it.station_id as number) ?? null,
            status: (it.status as Gateway['status']) ?? 'offline',
            firmwareVersion: (it.firmware_version as string) ?? null,
            lastOnline: (it.last_online as string) ?? null,
            ipAddress: (it.ip_address as string) ?? null,
            macAddress: (it.mac_address as string) ?? null,
            location: (it.location as string) ?? null,
            healthScore: (it.health_score as number) ?? 0,
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
            notes: (it.notes as string) ?? null,
          },
        };
      });
  },

  /** DELETE /gateways/{id} — 删除网关 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/gateways/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      return { ...raw, data: null };
    });
  },
};


// =====================
// VPP 虚拟电厂 API (/vpp/resources, POST /vpp/dispatch)
// =====================
export const vppApi = {
  /** GET /vpp/resources — VPP资源清单(光伏/储能/EV/负荷) */
  getResources(): Promise<ApiResponse<VppResource[]>> {
    return api.get('/vpp/resources').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const items = (raw.data as unknown as Record<string, unknown>[]) ?? [];
      return {
        ...raw,
        data: items.map((item): VppResource => ({
          resourceId: (item.resource_id as string) ?? '',
          resourceType: (item.resource_type as VppResourceType) ?? 'pv',
          stationId: (item.station_id as string) ?? '',
          ratedPowerKw: (item.rated_power_kw as number) ?? 0,
          currentPowerKw: (item.current_power_kw as number) ?? 0,
          availablePowerKw: (item.available_power_kw as number) ?? 0,
          soc: item.soc !== undefined && item.soc !== null ? (item.soc as number) : null,
          efficiency: (item.efficiency as number) ?? 0,
          priority: (item.priority as number) ?? 0,
          costPerKwh: (item.cost_per_kwh as number) ?? 0,
        })),
      };
    });
  },

  /** POST /vpp/dispatch — 触发VPP调度(削峰/填谷/调频/需求响应) */
  dispatch(body?: Record<string, unknown>): Promise<ApiResponse<VppDispatchPlan>> {
    return api.post('/vpp/dispatch', body ?? {}).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const commands = (d.commands as Record<string, unknown>[]) ?? [];
      return {
        ...raw,
        data: {
          planId: (d.plan_id as string) ?? '',
          mode: (d.mode as VppDispatchMode) ?? 'peak_shaving',
          trigger: (d.trigger as string) ?? '',
          stationsInvolved: (d.stations_involved as string[]) ?? [],
          totalDispatchKw: (d.total_dispatch_kw as number) ?? 0,
          estimatedRevenue: (d.estimated_revenue as number) ?? 0,
          estimatedCost: (d.estimated_cost as number) ?? 0,
          netProfit: (d.net_profit as number) ?? 0,
          commands: commands.map((c): VppDispatchCommand => ({
            resourceId: (c.resource_id as string) ?? '',
            stationId: (c.station_id as string) ?? '',
            resourceType: (c.resource_type as VppResourceType) ?? 'battery',
            targetPowerKw: (c.target_power_kw as number) ?? 0,
            durationMin: (c.duration_min as number) ?? 0,
            priority: (c.priority as number) ?? 0,
            estimatedRevenue: (c.estimated_revenue as number) ?? 0,
            estimatedCost: (c.estimated_cost as number) ?? 0,
            dispatchMode: (c.dispatch_mode as VppDispatchMode) ?? 'peak_shaving',
          })),
          createdAt: (d.created_at as string) ?? '',
        },
      };
    });
  },

  /** GET /vpp/dispatch/history — VPP调度历史记录 */
  getDispatchHistory(): Promise<ApiResponse<VppDispatchHistory[]>> {
    return api.get('/vpp/dispatch/history').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const items = (raw.data as unknown as Record<string, unknown>[]) ?? [];
      return {
        ...raw,
        data: items.map((item): VppDispatchHistory => ({
          planId: (item.plan_id as string) ?? '',
          mode: (item.mode as VppDispatchMode) ?? 'peak_shaving',
          trigger: (item.trigger as string) ?? '',
          stationsInvolved: (item.stations_involved as string[]) ?? [],
          totalDispatchKw: (item.total_dispatch_kw as number) ?? 0,
          estimatedRevenue: (item.estimated_revenue as number) ?? 0,
          estimatedCost: (item.estimated_cost as number) ?? 0,
          netProfit: (item.net_profit as number) ?? 0,
          commandsCount: (item.commands_count as number) ?? 0,
          createdAt: (item.created_at as string) ?? '',
          executed: (item.executed as boolean) ?? false,
        })),
      };
    });
  },
};


// =====================
// AI 对话 API (POST /chat)
// =====================
/** @cloud-down 2026-08-18 F1397: POST /chat → 404 (still down since F1368, was 200 降级 in F1367 (6th round)) */
export const chatApi = {
  /** POST /chat — 发送消息给AI助手 */
  send(message: string, options?: {
    conversationId?: string;
    context?: Record<string, unknown>;
  }): Promise<ApiResponse<ChatResponse>> {
    const body: Record<string, unknown> = { message };
    if (options?.conversationId) body.conversation_id = options.conversationId;
    if (options?.context) body.context = options.context;
    return api.post('/chat', body).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const sources = (d.sources as Record<string, unknown>[]) ?? [];
      const actions = (d.actions as Record<string, unknown>[]) ?? [];
      const usage = d.usage as Record<string, unknown> | null;
      return {
        ...raw,
        data: {
          answer: (d.answer as string) ?? '',
          confidence: (d.confidence as number) ?? 0,
          sources: sources.map((s): ChatSource => ({
            title: (s.title as string) ?? '',
            url: (s.url as string) ?? '',
            type: (s.type as string) ?? '',
          })),
          actions: actions.map((a): ChatAction => ({
            type: (a.type as string) ?? '',
            label: (a.label as string) ?? '',
            target: (a.target as string) ?? '',
          })),
          needsHuman: (d.needs_human as boolean) ?? false,
          usage: usage ? {
            promptTokens: (usage.prompt_tokens as number) ?? 0,
            completionTokens: (usage.completion_tokens as number) ?? 0,
            totalTokens: (usage.total_tokens as number) ?? 0,
          } : null,
        },
      };
    });
  },
};


// =====================
// 系统健康检查 API (GET /readyz + GET /livez + GET /health)
// =====================
export const healthApi = {
  /** GET /readyz — 详细就绪检查 (数据库/Redis/MQTT/文件系统) */
  getReadyz(): Promise<ApiResponse<SystemHealth>> {
    return api.get('/readyz').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const checks = (d.checks ?? {}) as Record<string, unknown>;
      const db = (checks.database ?? {}) as Record<string, unknown>;
      const redis = (checks.redis ?? {}) as Record<string, unknown>;
      const mqtt = (checks.mqtt_broker ?? {}) as Record<string, unknown>;
      const fs = (checks.filesystem ?? {}) as Record<string, unknown>;
      const fsPaths = (fs.paths ?? {}) as Record<string, Record<string, unknown>>;
      const paths: Record<string, { totalGb: number; freeGb: number; freePct: number }> = {};
      for (const [k, v] of Object.entries(fsPaths)) {
        paths[k] = {
          totalGb: (v.total_gb as number) ?? 0,
          freeGb: (v.free_gb as number) ?? 0,
          freePct: (v.free_pct as number) ?? 0,
        };
      }
      return {
        ...raw,
        data: {
          status: (d.status as HealthStatus) ?? 'error',
          checks: {
            database: {
              status: (db.status as HealthStatus) ?? 'error',
              poolSize: (db.pool_size as number) ?? 0,
              activeConnections: (db.active_connections as number) ?? 0,
              idleConnections: (db.idle_connections as number) ?? 0,
              waitingConnections: (db.waiting_connections as number) ?? 0,
              dbType: (db.db_type as string) ?? 'unknown',
            },
            redis: {
              status: (redis.status as HealthStatus) ?? 'error',
              version: (redis.version as string) ?? 'unknown',
              usedMemoryHuman: (redis.used_memory_human as string) ?? '0',
              connectedClients: (redis.connected_clients as number) ?? 0,
            },
            mqttBroker: {
              status: (mqtt.status as HealthStatus) ?? 'error',
              host: (mqtt.host as string) ?? 'unknown',
              port: (mqtt.port as number) ?? 0,
              error: (mqtt.error as string) ?? null,
            },
            filesystem: { paths },
          },
          uptimeSeconds: (d.uptime_seconds as number) ?? 0,
          unhealthyChecks: (d.unhealthy_checks as string[]) ?? [],
        },
      };
    });
  },

  /** GET /livez — 存活探针 */
  getLivez(): Promise<LivenessProbe> {
    return api.get('/livez').then((res) => {
      const d = (res.data ?? {}) as Record<string, unknown>;
      return {
        status: (d.status as string) ?? 'unknown',
        uptimeSeconds: (d.uptime_seconds as number) ?? 0,
      };
    });
  },

  /** GET /ping — 连通性检查 (返回pong) */
  getPing(): Promise<ApiResponse<{ message: string }>> {
    return api.get('/ping').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          message: (d.message as string) ?? '',
        },
      };
    });
  },

  /** GET /health — 简要健康信息 */
  getHealth(): Promise<ApiResponse<HealthInfo>> {
    return api.get('/health').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          status: (d.status as string) as HealthStatus ?? 'error',
          version: (d.version as string) ?? 'unknown',
          service: (d.service as string) ?? 'unknown',
        },
      };
    });
  },
};


// =====================
// 缓存统计 API (GET /cache/stats)
// =====================
export const cacheApi = {
  /** GET /cache/stats — Redis 缓存统计 (命中率/键数/内存/后端) */
  getStats(): Promise<ApiResponse<CacheStats>> {
    return api.get('/cache/stats').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          hitRate: (d.hit_rate as number) ?? 0,
          totalKeys: (d.total_keys as number) ?? 0,
          usedMemoryMb: (d.used_memory_mb as number) ?? 0,
          backend: (d.backend as string) ?? 'unknown',
        },
      };
    });
  },
};

