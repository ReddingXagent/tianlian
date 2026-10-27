/**
 * types/modules/security.ts — 安全/自愈/API密钥/营收分析类型
 */
// 安全审计日志 (SecurityLog — from /security/logs)
export interface SecurityLog {
  id: number;
  timestamp: string;
  userId: number;
  username: string;
  userRole: string | null;
  action: string;
  module: string;
  targetId: string;
  targetDesc: string;
  detail: string | null;
  oldValue: string | null;
  newValue: string | null;
  ipAddress: string | null;
  userAgent: string | null;
  result: 'success' | 'failure';
  errorMsg: string | null;
}

// 安全策略 (SecurityPolicy — from /security/policies)
export interface SecurityPolicy {
  id: number;
  policyKey: string;
  policyConfig: Record<string, unknown>;
  description: string;
  status: 'active' | 'inactive';
  createdAt: string;
  updatedAt: string;
}

// 安全威胁 (SecurityThreat — from /security/threats)
export interface SecurityThreat {
  id: number;
  type: string;
  sourceIp: string;
  target: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  status: 'blocked' | 'active' | 'resolved';
  timestamp: string;
}

// 自愈规则 (HealingRule — from /healing/rules)
export interface HealingRule {
  id: number;
  name: string;
  description: string;
  alarmPattern: Record<string, unknown>;
  runbookTemplate: string | null;
  autoApprove: boolean;
  maxRetries: number;
  cooldownMinutes: number;
  priority: number;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface HealingRuleCreate {
  name: string;
  alarmPattern: Record<string, unknown>;
  description?: string;
  runbookTemplate?: string | null;
  autoApprove?: boolean;
  maxRetries?: number;
  cooldownMinutes?: number;
  priority?: number;
  enabled?: boolean;
}

export interface HealingRuleUpdate {
  name?: string;
  description?: string;
  alarmPattern?: Record<string, unknown>;
  runbookTemplate?: string | null;
  autoApprove?: boolean;
  maxRetries?: number;
  cooldownMinutes?: number;
  priority?: number;
  enabled?: boolean;
}

// 自愈执行记录 (HealingExecution — from /healing/executions)
export interface HealingExecution {
  id: number;
  ruleId: number;
  ruleName: string;
  deviceId: number;
  deviceName: string;
  stationId: number;
  stationName: string;
  triggeredAt: string;
  status: string;
  actionTaken: string;
  result: string | null;
  duration: number;
  errorMessage: string | null;
  createdAt: string;
}

// 自愈统计 (HealingStats — from /healing/stats)
export interface HealingStats {
  total: number;
  statusBreakdown: Record<string, number>;
  successRate: number;
  averageDurationMs: number;
  autoApproveRate: number;
  pendingApprovals: number;
}

// API密钥 (ApiKey — from /api-keys)
export interface ApiKey {
  id: number;
  name: string;
  keyPrefix: string;
  description: string | null;
  scopes: string[];
  rateLimit: number;
  isActive: boolean;
  isRevoked: boolean;
  lastUsedAt: string | null;
  expiresAt: string | null;
  createdAt: string;
}

export interface ApiKeyUsage {
  keyId: number;
  periodDays: number;
  totalRequests: number;
  avgDurationMs: number;
}

export interface ApiKeyRotated {
  id: number;
  apiKey: string;
  keyPrefix: string;
}

export interface ApiKeyCreate {
  name: string;
  scopes: string[];
  description?: string;
  rateLimit?: number;
  expiresAt?: string | null;
}

export interface ApiKeyCreated {
  id: number;
  name: string;
  apiKey: string;
  keyPrefix: string;
  scopes: string[];
  expiresAt: string | null;
}

export interface ApiKeyUpdate {
  name?: string;
  description?: string;
  scopes?: string[];
  rateLimit?: number;
  isActive?: boolean;
  expiresAt?: string | null;
}

// 营收分析 (RevenueAnalytics — from /analytics/revenue)
export interface RevenueAnalyticsSummary {
  totalRevenue: number;
  totalKwh: number;
  totalOrders: number;
  avgPerOrder: number;
}

export interface RevenueAnalytics {
  summary: RevenueAnalyticsSummary;
  trend: unknown[];
}
