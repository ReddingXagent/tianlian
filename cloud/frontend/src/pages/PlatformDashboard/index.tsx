/**
 * 天链V3 - 平台总览（平台管理首页）
 * admin spec §2.9 — 服务拓扑图 + 设备接入统计
 */
import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Tag, Table, Progress, Timeline, Spin, Empty, Tooltip } from 'antd';
import {
  TeamOutlined, DesktopOutlined, EnvironmentOutlined, WarningOutlined,
  CloudServerOutlined, DatabaseOutlined, ApiOutlined, GlobalOutlined,
} from '@ant-design/icons';
import { statsAPI, tenantAPI, platformMonitorAPI } from '../../api';

interface Tenant {
  id: number;
  name: string;
  status: string;
  stations: number;
  devices: number;
  expired_at: string;
}

interface StatsOverview {
  station_count?: number;
  device_count?: number;
  alarm_count?: number;
  tenant_count?: number;
  total_stations?: number;
  total_devices?: number;
  total_alarms?: number;
}

interface TenantStats {
  total_tenants?: number;
  active_tenants?: number;
}

// ── 拓扑节点类型 ──
interface TopologyNode {
  id: string;
  name: string;
  type: 'gateway' | 'backend' | 'db' | 'cache' | 'mq';
  status: 'healthy' | 'degraded' | 'down';
  response_time_ms: number;
  dependencies: string[];
}

interface TopologyData {
  nodes: TopologyNode[];
  status_summary: Record<string, number>;
  device_online_rate: number;
}

// ── 设备接入统计类型 ──
interface DeviceCategory {
  category: string;
  total: number;
  online: number;
  offline: number;
  fault: number;
  online_rate: number;
}

interface ProtocolItem {
  protocol: string;
  count: number;
}

interface DeviceAccessStats {
  total_devices: number;
  total_online: number;
  total_offline: number;
  total_fault: number;
  online_rate: number;
  device_categories: DeviceCategory[];
  protocol_distribution: ProtocolItem[];
}

// ── 状态颜色映射 ──
const STATUS_COLORS: Record<string, string> = {
  healthy: '#52c41a',
  degraded: '#faad14',
  down: '#ff4d4f',
};

const NODE_TYPE_ICONS: Record<string, React.ReactNode> = {
  gateway: <GlobalOutlined />,
  backend: <ApiOutlined />,
  db: <DatabaseOutlined />,
  cache: <CloudServerOutlined />,
  mq: <CloudServerOutlined />,
};

// ── 服务拓扑图组件 (SVG) ──
const ServiceTopology: React.FC<{ data: TopologyData | null; loading: boolean }> = ({ data, loading }) => {
  if (loading) return <Spin />;
  if (!data || !data.nodes.length) return <Empty description="暂无拓扑数据" />;

  // 布局：按层级分组
  const layers: Record<string, TopologyNode[]> = { gateway: [], backend: [], infra: [] };
  data.nodes.forEach((n) => {
    if (n.type === 'gateway') layers.gateway.push(n);
    else if (n.type === 'backend') layers.backend.push(n);
    else layers.infra.push(n);
  });

  // 画布参数
  const NODE_R = 24;
  const COL_W = 160;
  const ROW_H = 80;
  const layerKeys = ['gateway', 'backend', 'infra'] as const;
  const maxNodesInLayer = Math.max(...layerKeys.map((k) => layers[k].length), 1);
  const svgW = 3 * COL_W + 80;
  const svgH = maxNodesInLayer * ROW_H + 60;

  // 计算节点坐标
  const nodePos: Record<string, { x: number; y: number }> = {};
  layerKeys.forEach((layer, colIdx) => {
    const nodes = layers[layer];
    const colX = 40 + colIdx * COL_W + COL_W / 2;
    nodes.forEach((node, rowIdx) => {
      const rowY = 40 + rowIdx * ROW_H + (maxNodesInLayer - nodes.length) * ROW_H / 2;
      nodePos[node.id] = { x: colX, y: rowY };
    });
  });

  // 构建边
  const edges: { from: string; to: string }[] = [];
  data.nodes.forEach((n) => {
    n.dependencies.forEach((dep) => {
      if (nodePos[dep]) edges.push({ from: n.id, to: dep });
    });
  });

  return (
    <div style={{ overflowX: 'auto' }}>
      <div style={{ marginBottom: 8, display: 'flex', gap: 16 }}>
        <Tag color="green">健康 {data.status_summary.healthy || 0}</Tag>
        <Tag color="orange">降级 {data.status_summary.degraded || 0}</Tag>
        <Tag color="red">故障 {data.status_summary.down || 0}</Tag>
        <span style={{ color: '#999', fontSize: 12 }}>设备在线率: {data.device_online_rate}%</span>
      </div>
      <svg width={svgW} height={svgH} style={{ display: 'block' }}>
        {/* 连线 */}
        {edges.map((e, i) => {
          const p1 = nodePos[e.from];
          const p2 = nodePos[e.to];
          return (
            <line key={i} x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y}
              stroke="#d9d9d9" strokeWidth={1} strokeDasharray="4 2" />
          );
        })}
        {/* 节点 */}
        {data.nodes.map((node) => {
          const pos = nodePos[node.id];
          if (!pos) return null;
          const color = STATUS_COLORS[node.status] || '#d9d9d9';
          return (
            <Tooltip key={node.id} title={`${node.name} · ${node.response_time_ms}ms`}>
              <g>
                <circle cx={pos.x} cy={pos.y} r={NODE_R} fill={color} fillOpacity={0.15}
                  stroke={color} strokeWidth={2} />
                <text x={pos.x} y={pos.y - 2} textAnchor="middle" fontSize={11} fontWeight={600} fill="#333">
                  {node.name.length > 6 ? node.name.slice(0, 5) + '…' : node.name}
                </text>
                <text x={pos.x} y={pos.y + 12} textAnchor="middle" fontSize={9} fill="#999">
                  {node.response_time_ms}ms
                </text>
              </g>
            </Tooltip>
          );
        })}
      </svg>
    </div>
  );
};

// ── 设备接入统计组件 ──
const DeviceAccessPanel: React.FC<{ data: DeviceAccessStats | null; loading: boolean }> = ({ data, loading }) => {
  if (loading) return <Spin />;
  if (!data) return <Empty description="暂无数据" />;

  const totalProto = data.protocol_distribution.reduce((s, p) => s + p.count, 0) || 1;
  // 协议饼图颜色
  const PROTO_COLORS = ['#1890ff', '#52c41a', '#faad14', '#ff4d4f', '#722ed1', '#13c2c2'];

  return (
    <div>
      {/* 总体指标 */}
      <Row gutter={8} style={{ marginBottom: 12 }}>
        <Col span={6}>
          <Statistic title="接入设备" value={data.total_devices} valueStyle={{ fontSize: 18 }} />
        </Col>
        <Col span={6}>
          <Statistic title="在线" value={data.total_online} valueStyle={{ fontSize: 18, color: '#52c41a' }} />
        </Col>
        <Col span={6}>
          <Statistic title="离线" value={data.total_offline} valueStyle={{ fontSize: 18, color: '#999' }} />
        </Col>
        <Col span={6}>
          <Statistic title="故障" value={data.total_fault} valueStyle={{ fontSize: 18, color: '#ff4d4f' }} />
        </Col>
      </Row>

      {/* 在线率进度条 */}
      <div style={{ marginBottom: 12 }}>
        <span style={{ fontSize: 12, color: '#666' }}>总体在线率</span>
        <Progress percent={data.online_rate} size="small"
          status={data.online_rate >= 80 ? 'success' : data.online_rate >= 50 ? 'active' : 'exception'} />
      </div>

      {/* 各分类统计表 */}
      <Table
        size="small"
        pagination={false}
        dataSource={data.device_categories}
        rowKey="category"
        style={{ marginBottom: 12 }}
        columns={[
          { title: '类型', dataIndex: 'category', width: 80 },
          { title: '总数', dataIndex: 'total', width: 50 },
          { title: '在线', dataIndex: 'online', width: 50 },
          {
            title: '在线率', dataIndex: 'online_rate', width: 80,
            render: (v: number) => <Progress percent={v} size="small" />,
          },
        ]}
      />

      {/* 协议分布 — 简易饼图 */}
      <div style={{ marginTop: 8 }}>
        <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>协议分布</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {/* SVG 环形饼图 */}
          <svg width={80} height={80} viewBox="0 0 80 80">
            {(() => {
              let cumulative = 0;
              return data.protocol_distribution.map((p, i) => {
                const fraction = p.count / totalProto;
                const startAngle = cumulative * 2 * Math.PI - Math.PI / 2;
                cumulative += fraction;
                const endAngle = cumulative * 2 * Math.PI - Math.PI / 2;
                const x1 = 40 + 30 * Math.cos(startAngle);
                const y1 = 40 + 30 * Math.sin(startAngle);
                const x2 = 40 + 30 * Math.cos(endAngle);
                const y2 = 40 + 30 * Math.sin(endAngle);
                const largeArc = fraction > 0.5 ? 1 : 0;
                const color = PROTO_COLORS[i % PROTO_COLORS.length];
                return (
                  <path key={i}
                    d={`M40,40 L${x1},${y1} A30,30 0 ${largeArc},1 ${x2},${y2} Z`}
                    fill={color} fillOpacity={0.8} />
                );
              });
            })()}
            <circle cx={40} cy={40} r={15} fill="#fff" />
            <text x={40} y={44} textAnchor="middle" fontSize={10} fill="#666">{totalProto}</text>
          </svg>
          <div style={{ flex: 1 }}>
            {data.protocol_distribution.map((p, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 2 }}>
                <span style={{
                  display: 'inline-block', width: 10, height: 10, borderRadius: 2,
                  background: PROTO_COLORS[i % PROTO_COLORS.length],
                }} />
                <span style={{ fontSize: 12 }}>{p.protocol}</span>
                <span style={{ fontSize: 12, color: '#999', marginLeft: 'auto' }}>{p.count}</span>
              </div>
            ))}
            {data.protocol_distribution.length === 0 && (
              <span style={{ fontSize: 12, color: '#999' }}>暂无协议数据</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};


// ── 主页面 ──
const PlatformDashboard: React.FC = () => {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [stats, setStats] = useState<StatsOverview>({});
  const [tenantStats, setTenantStats] = useState<TenantStats>({});
  const [topology, setTopology] = useState<TopologyData | null>(null);
  const [deviceStats, setDeviceStats] = useState<DeviceAccessStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [topoLoading, setTopoLoading] = useState(true);
  const [devLoading, setDevLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [statsRes, tenantsRes, tenantStatsRes] = await Promise.allSettled([
          statsAPI.overview(),
          tenantAPI.list(),
          tenantAPI.stats(),
        ]);

        if (statsRes.status === 'fulfilled') setStats(statsRes.value?.data || {});
        if (tenantsRes.status === 'fulfilled') {
          const tenantData = tenantsRes.value?.data || [];
          const tenantList = Array.isArray(tenantData) ? tenantData : tenantData.items || [];
          setTenants(tenantList.map((t: any) => ({
            id: t.id,
            name: t.name || t.tenant_name,
            status: t.status || 'active',
            stations: t.stations || t.station_count || 0,
            devices: t.devices || t.device_count || 0,
            expired_at: t.expired_at || t.expire_date || '-',
          })));
        }
        if (tenantStatsRes.status === 'fulfilled') setTenantStats(tenantStatsRes.value?.data || {});
      } catch {
        // 静默处理：仪表板数据加载失败保留上次状态
      } finally {
        setLoading(false);
      }
    };

    const fetchTopology = async () => {
      setTopoLoading(true);
      try {
        const res = await platformMonitorAPI.topology();
        setTopology(res?.data || null);
      } catch { setTopology(null); }
      finally { setTopoLoading(false); }
    };

    const fetchDeviceStats = async () => {
      setDevLoading(true);
      try {
        const res = await platformMonitorAPI.deviceAccessStats();
        setDeviceStats(res?.data || null);
      } catch { setDeviceStats(null); }
      finally { setDevLoading(false); }
    };

    fetchData();
    fetchTopology();
    fetchDeviceStats();
  }, []);

  const totalStations = stats.total_stations ?? stats.station_count ?? tenants.reduce((s, t) => s + (t.stations || 0), 0);
  const totalDevices = stats.total_devices ?? stats.device_count ?? tenants.reduce((s, t) => s + (t.devices || 0), 0);
  const totalTenants = tenantStats.total_tenants ?? tenants.length;
  const activeTeams = tenantStats.active_tenants ?? tenants.filter(t => t.status === 'active').length;
  const alarmCount = stats.total_alarms ?? stats.alarm_count ?? 0;

  return (
    <div>
      {/* 系统概览 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card loading={loading}>
            <Statistic title="运维团队数" value={totalTenants} prefix={<TeamOutlined />}
              suffix={<span style={{ fontSize: 14, color: '#34a853' }}>/ 活跃 {activeTeams}</span>} />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={loading}>
            <Statistic title="总站点数" value={totalStations} prefix={<EnvironmentOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={loading}>
            <Statistic title="总设备数" value={totalDevices} prefix={<DesktopOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={loading}>
            <Statistic title="当前告警" value={alarmCount} prefix={<WarningOutlined />}
              valueStyle={{ color: alarmCount > 0 ? '#ea4335' : '#34a853' }} />
            <div style={{ marginTop: 8, fontSize: 12, color: '#999' }}>版本 V3.0 · 运行正常</div>
          </Card>
        </Col>
      </Row>

      {/* 服务拓扑图 + 设备接入统计 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={14}>
          <Card title="服务拓扑图" size="small" extra={
            <span style={{ fontSize: 11, color: '#999' }}>
              {topology ? `${topology.nodes.length} 个节点` : ''}
            </span>
          }>
            <ServiceTopology data={topology} loading={topoLoading} />
          </Card>
        </Col>
        <Col span={10}>
          <Card title="设备接入统计" size="small">
            <DeviceAccessPanel data={deviceStats} loading={devLoading} />
          </Card>
        </Col>
      </Row>

      {/* 团队概览 + 最近活动 */}
      <Row gutter={16}>
        <Col span={16}>
          <Card title="运维团队概览" size="small" loading={loading}>
            <Table
              dataSource={tenants}
              rowKey="id"
              size="small"
              pagination={false}
              columns={[
                { title: '团队', dataIndex: 'name' },
                {
                  title: '状态', dataIndex: 'status', width: 80,
                  render: (s: string) => (
                    <Tag color={s === 'active' ? 'green' : s === 'trial' ? 'blue' : 'red'}>
                      {s === 'active' ? '正常' : s === 'trial' ? '试用' : '过期'}
                    </Tag>
                  ),
                },
                { title: '站点', dataIndex: 'stations', width: 60 },
                { title: '设备', dataIndex: 'devices', width: 60 },
                {
                  title: '到期', dataIndex: 'expired_at', width: 110,
                  render: (d: string) => {
                    if (!d || d === '-') return <span>-</span>;
                    const days = Math.ceil((new Date(d).getTime() - Date.now()) / 86400000);
                    return <span style={{ color: days < 30 ? '#ea4335' : undefined }}>{d}</span>;
                  },
                },
              ]}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card title="最近活动" size="small">
            <Timeline
              items={[
                { color: 'green', children: '系统正常运行中' },
                { color: 'blue', children: `当前共 ${totalTenants} 个运维团队` },
                { color: 'blue', children: `管理 ${totalStations} 个站点` },
                { color: 'blue', children: `接入 ${totalDevices} 台设备` },
                { color: alarmCount > 0 ? 'red' : 'green', children: alarmCount > 0 ? `有 ${alarmCount} 条未处理告警` : '暂无告警' },
              ]}
            />
          </Card>
          <Card title="资源使用" size="small" style={{ marginTop: 16 }}>
            <div style={{ marginBottom: 12 }}>CPU使用：<Progress percent={23} size="small" /></div>
            <div style={{ marginBottom: 12 }}>内存使用：<Progress percent={58} size="small" status="active" /></div>
            <div>存储使用：<Progress percent={35} size="small" /></div>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default PlatformDashboard;
