/**
 * types/modules/health.ts — 系统健康/Runbook/缓存类型
 */
export type HealthStatus = 'ok' | 'degraded' | 'error';

export interface DatabaseHealthCheck {
  status: HealthStatus;
  poolSize: number;
  activeConnections: number;
  idleConnections: number;
  waitingConnections: number;
  dbType: string;
}

export interface RedisHealthCheck {
  status: HealthStatus;
  version: string;
  usedMemoryHuman: string;
  connectedClients: number;
}

export interface MqttHealthCheck {
  status: HealthStatus;
  host: string;
  port: number;
  error: string | null;
}

export interface FilesystemPathInfo {
  totalGb: number;
  freeGb: number;
  freePct: number;
}

export interface FilesystemHealthCheck {
  paths: Record<string, FilesystemPathInfo>;
}

export interface SystemHealthChecks {
  database: DatabaseHealthCheck;
  redis: RedisHealthCheck;
  mqttBroker: MqttHealthCheck;
  filesystem: FilesystemHealthCheck;
  [key: string]: unknown;
}

export interface SystemHealth {
  status: HealthStatus;
  checks: SystemHealthChecks;
  uptimeSeconds: number;
  unhealthyChecks: string[];
}

export interface LivenessProbe {
  status: string;
  uptimeSeconds: number;
}

// Runbook 模板步骤 (from GET /runbooks/templates/{id})
export interface RunbookStep {
  stepId: number;
  actionType: string;
  description: string;
  command: string;
  params: Record<string, unknown>;
  riskLevel: string;
  timeoutSec: number;
  rollbackCommand: string;
  preCheck: string;
  postCheck: string;
  autoExecute: boolean;
  status: string;
  result: string;
  durationMs: number;
  errorMessage: string;
}

// Runbook 模板摘要 (from GET /runbooks/templates list)
export interface RunbookTemplateSummary {
  id: number;
  name: string;
  category: string;
  alarmType: string;
  description: string;
  stepCount: number;
  autoSteps: number;
  manualSteps: number;
  status: string;
  version: number;
  createdAt: string;
  updatedAt: string;
}

// Runbook 模板详情 (from GET /runbooks/templates/{id})
export interface RunbookTemplateDetail extends RunbookTemplateSummary {
  steps: RunbookStep[];
}

// 缓存统计 (from GET /cache/stats)
export interface CacheStats {
  hitRate: number;
  totalKeys: number;
  usedMemoryMb: number;
  backend: string;
}

// 设备健康度排名 (DeviceHealthRanking — from /health/devices)
export interface DeviceHealthOverall {
  totalDevices: number;
  healthyCount: number;
  warningCount: number;
  criticalCount: number;
  pendingEval: number;
  overallScore: number;
}

export interface DeviceHealthRankingItem {
  id: number;
  deviceName: string;
  code: string;
  type: string;
  stationName: string;
  score: number;
  status: string;
}

export interface DeviceHealthRanking {
  overall: DeviceHealthOverall;
  rankings: {
    best: DeviceHealthRankingItem[];
    worst: DeviceHealthRankingItem[];
  };
}
