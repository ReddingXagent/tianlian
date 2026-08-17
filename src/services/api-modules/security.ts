/**
 * api-modules/security.ts — 安全/密钥/愈合规则 API
 * 从 extended.ts 拆分 (F1361 维度22 领域细分)
 */
import api from './client';
import {
  ApiResponse,
  ApiKey,
  ApiKeyCreate,
  ApiKeyCreated,
  ApiKeyUpdate,
  ApiKeyUsage,
  ApiKeyRotated,
  SecurityLog,
  SecurityPolicy,
  SecurityThreat,
  RevenueAnalytics,
  HealingRule,
  HealingRuleCreate,
  HealingRuleUpdate,
  HealingExecution,
  HealingStats,
  PaginatedData,
} from '../../types';

// =====================
// 自愈规则 API (/healing/rules)
// =====================
export const healingRuleApi = {
  /** GET /healing/rules — 自愈规则列表 (返回数组) */
  getList(): Promise<ApiResponse<HealingRule[]>> {
    return api
      .get('/healing/rules')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const arr = (Array.isArray(raw.data) ? raw.data : []) as Record<string, unknown>[];
        return {
          ...raw,
          data: arr.map((it) => ({
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            description: (it.description as string) ?? '',
            alarmPattern: (it.alarm_pattern as Record<string, unknown>) ?? {},
            runbookTemplate: (it.runbook_template as string | null) ?? null,
            autoApprove: (it.auto_approve as boolean) ?? false,
            maxRetries: (it.max_retries as number) ?? 0,
            cooldownMinutes: (it.cooldown_minutes as number) ?? 0,
            priority: (it.priority as number) ?? 0,
            enabled: (it.enabled as boolean) ?? false,
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
          })),
        };
      });
  },

  /** GET /healing/rules/{id} — 自愈规则详情 */
  getById(id: number): Promise<ApiResponse<HealingRule>> {
    return api
      .get(`/healing/rules/${id}`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            description: (it.description as string) ?? '',
            alarmPattern: (it.alarm_pattern as Record<string, unknown>) ?? {},
            runbookTemplate: (it.runbook_template as string | null) ?? null,
            autoApprove: (it.auto_approve as boolean) ?? false,
            maxRetries: (it.max_retries as number) ?? 0,
            cooldownMinutes: (it.cooldown_minutes as number) ?? 0,
            priority: (it.priority as number) ?? 0,
            enabled: (it.enabled as boolean) ?? false,
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
          },
        };
      });
  },

  /** POST /healing/rules — 创建自愈规则 */
  create(body: HealingRuleCreate): Promise<ApiResponse<{ id: number; name: string; message: string }>> {
    return api
      .post('/healing/rules', {
        name: body.name,
        alarm_pattern: body.alarmPattern,
        description: body.description ?? '',
        runbook_template: body.runbookTemplate ?? null,
        auto_approve: body.autoApprove ?? false,
        max_retries: body.maxRetries ?? 1,
        cooldown_minutes: body.cooldownMinutes ?? 30,
        priority: body.priority ?? 0,
        enabled: body.enabled ?? true,
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (d.id as number) ?? 0,
            name: (d.name as string) ?? '',
            message: (d.message as string) ?? '',
          },
        };
      });
  },

  /** PUT /healing/rules/{id} — 更新自愈规则 */
  update(id: number, body: HealingRuleUpdate): Promise<ApiResponse<HealingRule>> {
    const payload: Record<string, unknown> = {};
    if (body.name !== undefined) payload.name = body.name;
    if (body.description !== undefined) payload.description = body.description;
    if (body.alarmPattern !== undefined) payload.alarm_pattern = body.alarmPattern;
    if (body.runbookTemplate !== undefined) payload.runbook_template = body.runbookTemplate;
    if (body.autoApprove !== undefined) payload.auto_approve = body.autoApprove;
    if (body.maxRetries !== undefined) payload.max_retries = body.maxRetries;
    if (body.cooldownMinutes !== undefined) payload.cooldown_minutes = body.cooldownMinutes;
    if (body.priority !== undefined) payload.priority = body.priority;
    if (body.enabled !== undefined) payload.enabled = body.enabled;
    return api.put(`/healing/rules/${id}`, payload).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          id: (d.id as number) ?? 0,
          name: (d.name as string) ?? '',
          description: (d.description as string) ?? '',
          alarmPattern: (d.alarm_pattern as Record<string, unknown>) ?? {},
          runbookTemplate: (d.runbook_template as string | null) ?? null,
          autoApprove: (d.auto_approve as boolean) ?? false,
          maxRetries: (d.max_retries as number) ?? 0,
          cooldownMinutes: (d.cooldown_minutes as number) ?? 0,
          priority: (d.priority as number) ?? 0,
          enabled: (d.enabled as boolean) ?? false,
          createdAt: (d.created_at as string) ?? '',
          updatedAt: (d.updated_at as string) ?? '',
        },
      };
    });
  },

  /** DELETE /healing/rules/{id} — 删除自愈规则 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/healing/rules/${id}`).then((res) => res.data);
  },
};


// =====================
// 自愈执行记录 API (/healing/executions)
// =====================
export const healingExecutionApi = {
  /** GET /healing/executions — 自愈执行记录列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<HealingExecution>>> {
    return api
      .get('/healing/executions', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          ruleId: (it.rule_id as number) ?? 0,
          ruleName: (it.rule_name as string) ?? '',
          deviceId: (it.device_id as number) ?? 0,
          deviceName: (it.device_name as string) ?? '',
          stationId: (it.station_id as number) ?? 0,
          stationName: (it.station_name as string) ?? '',
          triggeredAt: (it.triggered_at as string) ?? '',
          status: (it.status as string) ?? '',
          actionTaken: (it.action_taken as string) ?? '',
          result: (it.result as string | null) ?? null,
          duration: (it.duration as number) ?? 0,
          errorMessage: (it.error_message as string | null) ?? null,
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

  /** GET /healing/executions/{id} — 自愈执行记录详情 */
  getById(id: number): Promise<ApiResponse<HealingExecution>> {
    return api
      .get(`/healing/executions/${id}`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            ruleId: (it.rule_id as number) ?? 0,
            ruleName: (it.rule_name as string) ?? '',
            deviceId: (it.device_id as number) ?? 0,
            deviceName: (it.device_name as string) ?? '',
            stationId: (it.station_id as number) ?? 0,
            stationName: (it.station_name as string) ?? '',
            triggeredAt: (it.triggered_at as string) ?? '',
            status: (it.status as string) ?? '',
            actionTaken: (it.action_taken as string) ?? '',
            result: (it.result as string | null) ?? null,
            duration: (it.duration as number) ?? 0,
            errorMessage: (it.error_message as string | null) ?? null,
            createdAt: (it.created_at as string) ?? '',
          },
        };
      });
  },

  /** POST /healing/executions/{id}/retry — 重试自愈执行 */
  retry(id: number): Promise<ApiResponse<unknown>> {
    return api
      .post(`/healing/executions/${id}/retry`)
      .then((res) => res.data as ApiResponse<unknown>);
  },

  /** POST /healing/executions/{id}/approve — 批准自愈执行 */
  approve(id: number): Promise<ApiResponse<unknown>> {
    return api
      .post(`/healing/executions/${id}/approve`)
      .then((res) => res.data as ApiResponse<unknown>);
  },

  /** POST /healing/executions/{id}/reject — 拒绝自愈执行 */
  reject(id: number, reason?: string): Promise<ApiResponse<unknown>> {
    return api
      .post(`/healing/executions/${id}/reject`, { reason })
      .then((res) => res.data as ApiResponse<unknown>);
  },

  /** GET /healing/stats — 自愈统计数据 */
  getStats(): Promise<ApiResponse<HealingStats>> {
    return api
      .get('/healing/stats')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            total: (d.total as number) ?? 0,
            statusBreakdown: (d.status_breakdown as Record<string, number>) ?? {},
            successRate: (d.success_rate as number) ?? 0,
            averageDurationMs: (d.average_duration_ms as number) ?? 0,
            autoApproveRate: (d.auto_approve_rate as number) ?? 0,
            pendingApprovals: (d.pending_approvals as number) ?? 0,
          },
        };
      });
  },
};


// =====================
// API密钥 API (/api-keys)
// =====================
export const apiKeyApi = {
  /** POST /api-keys — 创建API密钥 (返回含明文api_key, 仅此一次可见) */
  create(body: ApiKeyCreate): Promise<ApiResponse<ApiKeyCreated>> {
    const payload: Record<string, unknown> = {
      name: body.name,
      scopes: body.scopes,
    };
    if (body.description !== undefined) payload.description = body.description;
    if (body.rateLimit !== undefined) payload.rate_limit = body.rateLimit;
    if (body.expiresAt !== undefined) payload.expires_at = body.expiresAt;
    return api
      .post('/api-keys', payload)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            apiKey: (it.api_key as string) ?? '',
            keyPrefix: (it.key_prefix as string) ?? '',
            scopes: (it.scopes as string[]) ?? [],
            expiresAt: (it.expires_at as string | null) ?? null,
          },
        };
      });
  },

  /** GET /api-keys — API密钥列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<ApiKey>>> {
    return api
      .get('/api-keys', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          keyPrefix: (it.key_prefix as string) ?? '',
          description: (it.description as string | null) ?? null,
          scopes: ((it.scopes as string[]) ?? []),
          rateLimit: (it.rate_limit as number) ?? 0,
          isActive: (it.is_active as boolean) ?? false,
          isRevoked: (it.is_revoked as boolean) ?? false,
          lastUsedAt: (it.last_used_at as string | null) ?? null,
          expiresAt: (it.expires_at as string | null) ?? null,
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

  /** GET /api-keys/{id} — API密钥详情 */
  getDetail(id: number): Promise<ApiResponse<ApiKey>> {
    return api
      .get(`/api-keys/${id}`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            keyPrefix: (it.key_prefix as string) ?? '',
            description: (it.description as string | null) ?? null,
            scopes: ((it.scopes as string[]) ?? []),
            rateLimit: (it.rate_limit as number) ?? 0,
            isActive: (it.is_active as boolean) ?? false,
            isRevoked: (it.is_revoked as boolean) ?? false,
            lastUsedAt: (it.last_used_at as string | null) ?? null,
            expiresAt: (it.expires_at as string | null) ?? null,
            createdAt: (it.created_at as string) ?? '',
          },
        };
      });
  },

  /** PUT /api-keys/{id} — 更新API密钥 */
  update(id: number, body: ApiKeyUpdate): Promise<ApiResponse<null>> {
    const payload: Record<string, unknown> = {};
    if (body.name !== undefined) payload.name = body.name;
    if (body.description !== undefined) payload.description = body.description;
    if (body.scopes !== undefined) payload.scopes = body.scopes;
    if (body.rateLimit !== undefined) payload.rate_limit = body.rateLimit;
    if (body.isActive !== undefined) payload.is_active = body.isActive;
    if (body.expiresAt !== undefined) payload.expires_at = body.expiresAt;
    return api
      .put(`/api-keys/${id}`, payload)
      .then((res) => res.data as ApiResponse<null>);
  },

  /** GET /api-keys/{id}/usage — API密钥使用统计 */
  getUsage(id: number): Promise<ApiResponse<ApiKeyUsage>> {
    return api
      .get(`/api-keys/${id}/usage`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            keyId: (d.key_id as number) ?? 0,
            periodDays: (d.period_days as number) ?? 0,
            totalRequests: (d.total_requests as number) ?? 0,
            avgDurationMs: (d.avg_duration_ms as number) ?? 0,
          },
        };
      });
  },

  /** POST /api-keys/{id}/rotate — 轮换API密钥 */
  rotate(id: number): Promise<ApiResponse<ApiKeyRotated>> {
    return api
      .post(`/api-keys/${id}/rotate`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (d.id as number) ?? 0,
            apiKey: (d.api_key as string) ?? '',
            keyPrefix: (d.key_prefix as string) ?? '',
          },
        };
      });
  },

  /** DELETE /api-keys/{id} — 删除API密钥 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api
      .delete(`/api-keys/${id}`)
      .then((res) => res.data as ApiResponse<null>);
  },
};

// =====================
// 安全审计日志 API (/security/logs)
// =====================
export const securityLogApi = {
  /** GET /security/logs — 安全审计日志列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<SecurityLog>>> {
    return api
      .get('/security/logs', {
        params: { page: params?.page, page_size: params?.pageSize },
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          timestamp: (it.timestamp as string) ?? '',
          userId: (it.user_id as number) ?? 0,
          username: (it.username as string) ?? '',
          userRole: (it.user_role as string | null) ?? null,
          action: (it.action as string) ?? '',
          module: (it.module as string) ?? '',
          targetId: (it.target_id as string) ?? '',
          targetDesc: (it.target_desc as string) ?? '',
          detail: (it.detail as string | null) ?? null,
          oldValue: (it.old_value as string | null) ?? null,
          newValue: (it.new_value as string | null) ?? null,
          ipAddress: (it.ip_address as string | null) ?? null,
          userAgent: (it.user_agent as string | null) ?? null,
          result: (it.result as 'success' | 'failure') ?? 'success',
          errorMsg: (it.error_msg as string | null) ?? null,
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
// 安全策略 API (/security/policies)
// =====================
export const securityPolicyApi = {
  /** GET /security/policies — 安全策略列表 */
  getList(): Promise<ApiResponse<PaginatedData<SecurityPolicy>>> {
    return api
      .get('/security/policies')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          policyKey: (it.policy_key as string) ?? '',
          policyConfig: (it.policy_config as Record<string, unknown>) ?? {},
          description: (it.description as string) ?? '',
          status: (it.status as 'active' | 'inactive') ?? 'active',
          createdAt: (it.created_at as string) ?? '',
          updatedAt: (it.updated_at as string) ?? '',
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? 0,
            page: 1,
            pageSize: items.length,
          },
        };
      });
  },

  /** GET /security/policies/{key} — 单个安全策略详情 */
  getByKey(key: string): Promise<ApiResponse<SecurityPolicy>> {
    return api
      .get(`/security/policies/${key}`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            policyKey: (it.policy_key as string) ?? '',
            policyConfig: (it.policy_config as Record<string, unknown>) ?? {},
            description: (it.description as string) ?? '',
            status: (it.status as 'active' | 'inactive') ?? 'active',
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
          },
        };
      });
  },
};


/**
 * 营收分析 API — /analytics/revenue
 * 支持可选查询参数: start_date, end_date, period, station_id
 */
export const analyticsRevenueApi = {
  /** GET /analytics/revenue — 营收分析汇总 */
  getSummary(params?: {
    startDate?: string;
    endDate?: string;
    period?: string;
    stationId?: number;
  }): Promise<ApiResponse<RevenueAnalytics>> {
    const query: Record<string, string> = {};
    if (params?.startDate) query.start_date = params.startDate;
    if (params?.endDate) query.end_date = params.endDate;
    if (params?.period) query.period = params.period;
    if (params?.stationId != null) query.station_id = String(params.stationId);
    return api
      .get('/analytics/revenue', { params: query })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const s = (d.summary as Record<string, unknown>) ?? {};
        return {
          ...raw,
          data: {
            summary: {
              totalRevenue: (s.total_revenue as number) ?? 0,
              totalKwh: (s.total_kwh as number) ?? 0,
              totalOrders: (s.total_orders as number) ?? 0,
              avgPerOrder: (s.avg_per_order as number) ?? 0,
            },
            trend: (d.trend as unknown[]) ?? [],
          },
        };
      });
  },
};


// =====================
// 安全威胁 API (/security/threats)
// =====================
export const securityThreatApi = {
  /** GET /security/threats — 安全威胁列表 */
  getList(): Promise<ApiResponse<PaginatedData<SecurityThreat>>> {
    return api
      .get('/security/threats')
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          type: (it.type as string) ?? '',
          sourceIp: (it.source_ip as string) ?? '',
          target: (it.target as string) ?? '',
          severity: (it.severity as 'low' | 'medium' | 'high' | 'critical') ?? 'low',
          status: (it.status as 'blocked' | 'active' | 'resolved') ?? 'active',
          timestamp: (it.timestamp as string) ?? '',
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? 0,
            page: 1,
            pageSize: items.length,
          },
        };
      });
  },
};

