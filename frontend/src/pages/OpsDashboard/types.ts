/**
 * 运维大屏类型定义
 *
 * Phase11 #59：实时拓扑 / 事件流 / 健康度评分数据契约
 */

export interface TopologyNode {
  id: string;
  type: 'station' | 'gateway' | 'device';
  name: string;
  status: string;
  health_score?: number;
  device_count?: number;
  online_count?: number;
  fault_count?: number;
  station_id?: number;
  gateway_id?: number | null;
  device_type?: string;
  position?: { lat: number; lng: number };
}

export interface TopologyEdge {
  source: string;
  target: string;
  type: string;
}

export interface TopologyData {
  nodes: {
    stations: TopologyNode[];
    gateways: TopologyNode[];
    devices: TopologyNode[];
  };
  edges: TopologyEdge[];
  summary: {
    total_stations: number;
    total_gateways: number;
    total_devices: number;
    online_devices: number;
    fault_devices: number;
  };
}

export interface EventItem {
  id: string;
  type: 'alarm' | 'workorder' | 'healing';
  title: string;
  level: string;
  status: string;
  station_name?: string;
  device_name?: string;
  alarm_type?: string;
  result?: string;
  created_at?: string;
  timestamp: string;
}

export interface HealthStation {
  station_id: number;
  station_name: string;
  health_score: number;
  device_health_avg: number;
  online_rate: number;
  device_count: number;
  online_count: number;
  fault_count: number;
  status: string;
}

export interface HealthData {
  overall_score: number;
  overall_online_rate: number;
  total_stations: number;
  total_devices: number;
  total_online: number;
  total_fault: number;
  distribution: {
    excellent: number;
    good: number;
    warning: number;
    fault: number;
  };
  stations: HealthStation[];
}

export interface OverviewStats {
  stats: {
    stations: number;
    devices: number;
    online: number;
    fault: number;
    online_rate: number;
  };
  alarms: {
    active: number;
    critical: number;
  };
  workorders: {
    pending: number;
    in_progress: number;
  };
  healing: {
    total_24h: number;
    success_24h: number;
    success_rate: number;
  };
  timestamp: string;
}

// ─── 拓扑图节点位置（Canvas 渲染 / 点击检测共用） ───

export interface NodePosition {
  x: number;
  y: number;
  node: TopologyNode;
  radius: number;
}
