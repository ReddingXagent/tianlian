/**
 * api-modules/alarm-notification.ts — 告警规则与通知 API
 * 从 extended.ts 拆分 (F1361 维度22 领域细分)
 */
import api from './client';
import {
  ApiResponse,
  AlarmRule,
  AlarmRuleCreate,
  AlarmRuleCreated,
  AlarmRuleUpdate,
  NotificationRule,
  NotificationRuleCreate,
  NotificationRuleCreated,
  NotificationRuleUpdate,
  NotificationTemplate,
  NotificationStats,
  PaginatedData,
  UnreadCount,
  ReadAllResult,
  NotificationSendResult,
} from '../../types';

export const alarmRuleApi = {
  /** GET /alarm-rules — 告警规则列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<AlarmRule>>> {
    return api.get('/alarm-rules', { params: { page: params?.page, page_size: params?.pageSize } }).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
        id: (it.id as number) ?? 0,
        name: (it.name as string) ?? '',
        deviceType: (it.device_type as string) ?? '',
        metric: (it.metric as string) ?? '',
        condition: (it.condition as string) ?? '',
        threshold: (it.threshold as number) ?? 0,
        level: ((it.level as string) ?? 'warning') as AlarmRule['level'],
        enabled: (it.enabled as boolean) ?? false,
        description: (it.description as string) ?? '',
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

  create(body: AlarmRuleCreate): Promise<ApiResponse<AlarmRuleCreated>> {
    return api
      .post('/alarm-rules', {
        name: body.name,
        metric: body.metric,
        threshold: body.threshold,
        ...(body.deviceType !== undefined && { device_type: body.deviceType }),
        ...(body.severity !== undefined && { severity: body.severity }),
        ...(body.operator !== undefined && { operator: body.operator }),
        ...(body.duration !== undefined && { duration: body.duration }),
        ...(body.enabled !== undefined && { enabled: body.enabled }),
        ...(body.description !== undefined && { description: body.description }),
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        if (!raw.data) return { ...raw, data: null } as unknown as ApiResponse<AlarmRuleCreated>;
        const d = raw.data as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (d.id as number) ?? 0,
            name: (d.name as string) ?? '',
            description: (d.description as string) ?? '',
            deviceType: (d.device_type as string | null) ?? null,
            deviceIds: (d.device_ids as number[] | null) ?? null,
            stationIds: (d.station_ids as number[] | null) ?? null,
            metric: (d.metric as string) ?? '',
            operator: (d.operator as string) ?? '>',
            threshold: (d.threshold as number) ?? 0,
            duration: (d.duration as number) ?? 0,
            level: (d.level as string) ?? 'warning',
            alarmTemplate: (d.alarm_template as string) ?? '',
            notifyUsers: (d.notify_users as string[] | null) ?? null,
            autoCreateWorkorder: (d.auto_create_workorder as boolean) ?? false,
            workorderPriority: (d.workorder_priority as string) ?? 'medium',
            enabled: (d.enabled as boolean) ?? false,
            silenceMinutes: (d.silence_minutes as number) ?? 0,
            createdAt: (d.created_at as string) ?? '',
            updatedAt: (d.updated_at as string | null) ?? null,
          },
        };
      });
  },

  /** PUT /alarm-rules/{id} — 更新告警规则 */
  update(id: number, body: AlarmRuleUpdate): Promise<ApiResponse<AlarmRuleCreated>> {
    return api
      .put(`/alarm-rules/${id}`, {
        ...(body.name !== undefined && { name: body.name }),
        ...(body.metric !== undefined && { metric: body.metric }),
        ...(body.threshold !== undefined && { threshold: body.threshold }),
        ...(body.deviceType !== undefined && { device_type: body.deviceType }),
        ...(body.severity !== undefined && { severity: body.severity }),
        ...(body.operator !== undefined && { operator: body.operator }),
        ...(body.duration !== undefined && { duration: body.duration }),
        ...(body.enabled !== undefined && { enabled: body.enabled }),
        ...(body.description !== undefined && { description: body.description }),
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        if (!raw.data) return { ...raw, data: null } as unknown as ApiResponse<AlarmRuleCreated>;
        const d = raw.data as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (d.id as number) ?? 0,
            name: (d.name as string) ?? '',
            description: (d.description as string) ?? '',
            deviceType: (d.device_type as string | null) ?? null,
            deviceIds: (d.device_ids as number[] | null) ?? null,
            stationIds: (d.station_ids as number[] | null) ?? null,
            metric: (d.metric as string) ?? '',
            operator: (d.operator as string) ?? '>',
            threshold: (d.threshold as number) ?? 0,
            duration: (d.duration as number) ?? 0,
            level: (d.level as string) ?? 'warning',
            alarmTemplate: (d.alarm_template as string) ?? '',
            notifyUsers: (d.notify_users as string[] | null) ?? null,
            autoCreateWorkorder: (d.auto_create_workorder as boolean) ?? false,
            workorderPriority: (d.workorder_priority as string) ?? 'medium',
            enabled: (d.enabled as boolean) ?? false,
            silenceMinutes: (d.silence_minutes as number) ?? 0,
            createdAt: (d.created_at as string) ?? '',
            updatedAt: (d.updated_at as string | null) ?? null,
          },
        };
      });
  },

  /** DELETE /alarm-rules/{id} — 删除告警规则 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/alarm-rules/${id}`).then((res) => res.data);
  },
};


// =====================
// 通知规则 API (GET /notification-rules)
// =====================
export const notificationRuleApi = {
  /** GET /notification-rules — 通知规则列表 */
  getList(): Promise<ApiResponse<NotificationRule[]>> {
    return api.get('/notification-rules').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>[] | unknown>;
      const items = (Array.isArray(raw.data) ? raw.data : []) as Record<string, unknown>[];
      return {
        ...raw,
        data: items.map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          event: (it.event as string) ?? '',
          channels: (it.channels as string[]) ?? [],
          recipients: (it.recipients as string[]) ?? [],
          enabled: (it.enabled as boolean) ?? false,
          template: (it.template as string) ?? '',
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        })),
      };
    });
  },

  /** POST /notification-rules — 创建通知规则 */
  create(body: NotificationRuleCreate): Promise<ApiResponse<NotificationRuleCreated>> {
    return api
      .post('/notification-rules', {
        name: body.name,
        level: body.level,
        ...(body.channels !== undefined && { channels: body.channels }),
        ...(body.receivers !== undefined && { receivers: body.receivers }),
        ...(body.enabled !== undefined && { enabled: body.enabled }),
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        if (!raw.data) return { ...raw, data: null } as unknown as ApiResponse<NotificationRuleCreated>;
        const d = raw.data as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (d.id as number) ?? 0,
            name: (d.name as string) ?? '',
            level: (d.level as string) ?? '',
            channels: (d.channels as string[]) ?? [],
            receivers: (d.receivers as string[]) ?? [],
            enabled: (d.enabled as boolean) ?? false,
            createdAt: (d.created_at as string) ?? '',
            updatedAt: (d.updated_at as string | null) ?? null,
          },
        };
      });
  },

  /** PUT /notification-rules/{id} — 更新通知规则 */
  update(id: number, body: NotificationRuleUpdate): Promise<ApiResponse<NotificationRuleCreated>> {
    return api
      .put(`/notification-rules/${id}`, {
        ...(body.name !== undefined && { name: body.name }),
        ...(body.level !== undefined && { level: body.level }),
        ...(body.channels !== undefined && { channels: body.channels }),
        ...(body.receivers !== undefined && { receivers: body.receivers }),
        ...(body.enabled !== undefined && { enabled: body.enabled }),
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        if (!raw.data) return { ...raw, data: null } as unknown as ApiResponse<NotificationRuleCreated>;
        const d = raw.data as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (d.id as number) ?? 0,
            name: (d.name as string) ?? '',
            level: (d.level as string) ?? '',
            channels: (d.channels as string[]) ?? [],
            receivers: (d.receivers as string[]) ?? [],
            enabled: (d.enabled as boolean) ?? false,
            createdAt: (d.created_at as string) ?? '',
            updatedAt: (d.updated_at as string | null) ?? null,
          },
        };
      });
  },

  /** DELETE /notification-rules/{id} — 删除通知规则 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/notification-rules/${id}`).then((res) => res.data);
  },
};


// =====================
// 通知模板 API (GET /notifications/templates)
// =====================
export const notificationTemplateApi = {
  /** GET /notifications/templates — 通知模板列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<NotificationTemplate>>> {
    return api
      .get('/notifications/templates', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          channel: (it.channel as string) ?? '',
          subject: (it.subject as string) ?? '',
          body: (it.body as string) ?? '',
          variables: (it.variables as string[]) ?? [],
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

  /** DELETE /notifications/templates/{id} — 删除通知模板 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/notifications/templates/${id}`).then((res) => res.data);
  },
};


// =====================
// 通知统计 API (/notifications/stats)
// =====================
export const notificationStatsApi = {
  /** GET /notifications/stats — 通知统计 */
  getStats(): Promise<ApiResponse<NotificationStats>> {
    return api
      .get('/notifications/stats')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            totalTemplates: (d.total_templates as number) ?? 0,
            totalMessages: (d.total_messages as number) ?? 0,
            sentToday: (d.sent_today as number) ?? 0,
            failedCount: (d.failed_count as number) ?? 0,
            channelDistribution: (d.channel_distribution as Record<string, number>) ?? {},
          },
        };
      });
  },
};


// =====================
// 未读通知计数 API (/notifications/unread-count)
// =====================
export const notificationUnreadApi = {
  /** GET /notifications/unread-count — 未读通知计数 */
  getUnreadCount(): Promise<ApiResponse<UnreadCount>> {
    return api
      .get('/notifications/unread-count')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            unreadCount: (d.unread_count as number) ?? 0,
          },
        };
      });
  },
};


// =====================
// 通知操作 API (POST /notifications/read-all, /notifications/{id}/read)
// =====================
export const notificationActionApi = {
  /** POST /notifications/read-all — 全部标记为已读 */
  readAll(): Promise<ApiResponse<ReadAllResult>> {
    return api
      .post('/notifications/read-all')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            markedCount: (d.marked_count as number) ?? 0,
          },
        };
      });
  },

  /** POST /notifications/{id}/read — 标记单条为已读 */
  readById(id: number | string): Promise<ApiResponse<null>> {
    return api.post(`/notifications/${id}/read`).then((res) => res.data as ApiResponse<null>);
  },
};


// =====================
// 通知发送 API (POST /notifications/send)
// =====================
export const notificationSendApi = {
  /** POST /notifications/send — 发送通知给指定用户 */
  send(params: {
    userId: number;
    title: string;
    content: string;
    channel?: string;
    type?: string;
  }): Promise<ApiResponse<NotificationSendResult>> {
    const body: Record<string, unknown> = {
      user_id: params.userId,
      title: params.title,
      content: params.content,
    };
    if (params.channel) body.channel = params.channel;
    if (params.type) body.type = params.type;
    return api.post('/notifications/send', body).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          status: (d.status as string) ?? '',
          channel: (d.channel as string) ?? null,
          userId: (d.user_id as string) ?? null,
          title: (d.title as string) ?? null,
          sentAt: (d.sent_at as string) ?? null,
        },
      };
    });
  },
};

