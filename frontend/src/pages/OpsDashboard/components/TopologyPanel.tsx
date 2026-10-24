/**
 * 左栏：实时拓扑（概览统计 + ECharts 树形拓扑 + 图例 + 点击详情浮卡）
 *
 * 2026-10-10 丁哥: 拓扑节点点击/悬停显示状态、故障类型 —
 * 悬停 tooltip: 站点(状态+设备统计) / 网关(状态) / 设备(类型+状态+健康度+最近故障)
 * 点击: 详情浮卡(节点信息 + 最近3条相关事件: 告警/工单/自愈)
 */
import React, { useMemo, useState } from 'react';
import {
  EnvironmentOutlined, ApiOutlined, DesktopOutlined,
  CheckCircleOutlined, WarningOutlined, ThunderboltOutlined, CloseOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { COLORS, STATUS_COLORS } from '../constants';
import type { TopologyData, TopologyNode, EventItem } from '../types';

interface TreeOpt {
  name: string;
  id?: string;
  children?: TreeOpt[];
  itemStyle?: { color: string; borderColor?: string; borderWidth?: number };
  symbolSize?: number;
  __raw?: TopologyNode;
}

const STATUS_TEXT: Record<string, string> = {
  online: '在线', normal: '正常', warning: '告警', fault: '故障',
  critical: '严重故障', offline: '离线',
};

const NODE_TYPE_TEXT: Record<string, string> = {
  station: '站点', gateway: '网关', device: '设备',
};

const TopologyPanel: React.FC<{
  topology: TopologyData | null;
  selectedNode: string | null;
  onNodeClick: (id: string) => void;
  events?: EventItem[];
}> = ({ topology, selectedNode, onNodeClick, events = [] }) => {
  const [detail, setDetail] = useState<TopologyNode | null>(null);
  const [resetKey, setResetKey] = useState(0);

  // 该节点相关事件(故障类型来源): 设备按 device_name, 站点按 station_name
  const nodeEvents = useMemo(() => {
    if (!detail) return [];
    return events
      .filter((e) =>
        (detail.type === 'device' && e.device_name === detail.name) ||
        (detail.type === 'station' && e.station_name === detail.name))
      .slice(0, 3);
  }, [detail, events]);

  // 组装树: 平台 → 站点 → 网关 → 设备 (设备永不直连平台根)
  const treeData = useMemo<TreeOpt>(() => {
    const idNum = (s: string) => Number(String(s).split('-')[1] || 0);
    const mk = (n: TopologyNode, size: number, fallbackColor: string): TreeOpt => ({
      name: n.name,
      id: n.id,
      symbolSize: size,
      __raw: n,
      itemStyle: {
        color: STATUS_COLORS[n.status] || fallbackColor,
        borderColor: selectedNode === n.id ? '#fff' : undefined,
        borderWidth: selectedNode === n.id ? 3 : 0,
      },
    });

    const stations = (topology?.nodes.stations || []).map((s) => {
      const stationNode = { ...mk(s, 22, COLORS.station), children: [] as TreeOpt[] };
      (stationNode as any).__stationNum = idNum(s.id);
      const gws = (topology?.nodes.gateways || []).filter(
        (g) => idNum(g.id) === idNum(s.id) || g.station_id === idNum(s.id),
      );
      gws.forEach((g) => {
        const gwNode = { ...mk(g, 14, COLORS.gateway), children: [] as TreeOpt[] };
        (topology?.nodes.devices || [])
          .filter((d) => d.gateway_id != null && `gateway-${d.gateway_id}` === g.id)
          .forEach((d) => gwNode.children.push(mk(d, 8, COLORS.deviceOffline)));
        stationNode.children.push(gwNode);
      });
      return stationNode;
    });

    const rootChildren: TreeOpt[] = [...stations];
    // 孤儿网关(无站点)挂根
    (topology?.nodes.gateways || []).filter(
      (g) => !(topology?.nodes.stations || []).some(
        (s) => idNum(g.id) === idNum(s.id) || g.station_id === idNum(s.id)),
    ).forEach((g) => {
      const gwNode = { ...mk(g, 14, COLORS.gateway), children: [] as TreeOpt[] };
      (topology?.nodes.devices || [])
        .filter((d) => d.gateway_id != null && `gateway-${d.gateway_id}` === g.id)
        .forEach((d) => gwNode.children.push(mk(d, 8, COLORS.deviceOffline)));
      rootChildren.push(gwNode);
    });
    // 无网关设备挂所属站点; 无站点进「未分配设备」组
    const unassigned: TreeOpt[] = [];
    (topology?.nodes.devices || []).filter((d) => d.gateway_id == null).forEach((d) => {
      const stationNode: any = stations.find(
        (st: any) => st.__stationNum === d.station_id,
      );
      if (stationNode) stationNode.children.push(mk(d, 8, COLORS.deviceOffline));
      else unassigned.push(mk(d, 8, COLORS.deviceOffline));
    });
    if (unassigned.length) {
      rootChildren.push({
        name: `未分配设备(${unassigned.length})`,
        symbolSize: 16,
        itemStyle: { color: COLORS.deviceOffline },
        children: unassigned,
      });
    }

    return {
      name: '天链平台',
      symbolSize: 26,
      itemStyle: { color: COLORS.accent },
      children: rootChildren,
    };
  }, [topology, selectedNode]);

  // tooltip: 状态/统计/故障
  const tooltipFormatter = (params: { data?: TreeOpt }) => {
    const d = params?.data;
    if (!d) return '';
    if (!d.__raw) return d.name; // 根/虚拟组
    const n = d.__raw;
    const status = STATUS_TEXT[n.status] || n.status;
    const lines: string[] = [`<b>${n.name}</b>`, `${NODE_TYPE_TEXT[n.type] || n.type} · ${status}`];
    if (n.type === 'station' && n.device_count != null) {
      lines.push(`设备 ${n.device_count} 台 · 在线 ${n.online_count ?? 0} · 故障 ${n.fault_count ?? 0}`);
    }
    if (n.type === 'device') {
      if (n.device_type) lines.push(`类型: ${n.device_type}`);
      if (n.health_score != null) lines.push(`健康度: ${Math.round(n.health_score)}`);
    }
    // 最近故障(设备/站点维度, 取1条最新告警)
    const ev = events.find((e) =>
      (n.type === 'device' && e.device_name === n.name) ||
      (n.type === 'station' && e.station_name === n.name));
    if (ev) lines.push(`<span style="color:${COLORS.danger}">最近: ${ev.title}</span>`);
    return lines.join('<br/>');
  };

  const option = useMemo(() => ({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item' as const,
      formatter: tooltipFormatter,
      backgroundColor: 'rgba(6, 20, 40, 0.92)',
      borderColor: COLORS.border,
      textStyle: { color: COLORS.text, fontSize: 12 },
      extraCssText: 'max-width: 260px; white-space: normal;',
    },
    series: [{
      type: 'tree' as const,
      data: [treeData],
      orient: 'RL' as const,
      left: 90, right: 8, top: 30, bottom: 8,
      roam: true,
      scaleLimit: { min: 0.4, max: 4 },  // 限制缩放范围, 防飞出
      expandAndCollapse: true,
      initialTreeDepth: -1,
      symbol: 'circle',
      lineStyle: { color: 'rgba(32, 160, 255, 0.3)', width: 1.2, curveness: 0.5 },
      label: {
        color: COLORS.text,
        fontSize: 11,
        position: 'left' as const,
        distance: 6,
        formatter: (p: { name: string }) =>
          p.name.length > 8 ? p.name.slice(0, 8) + '…' : p.name,
      },
      leaves: { label: { fontSize: 10, color: COLORS.textDim } },
      emphasis: { focus: 'ancestor' as const, itemStyle: { shadowBlur: 10, shadowColor: 'rgba(32,160,255,0.5)' } },
      animationDuration: 400,
    }],
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [treeData, events]);

  const handleNodeClick = (raw: TopologyNode | undefined, id?: string) => {
    if (raw) setDetail((prev) => (prev?.id === raw.id ? null : raw));
    if (id) onNodeClick(id);
  };

  const statusColor = (n: TopologyNode) =>
    STATUS_COLORS[n.status] || (n.type === 'station' ? COLORS.station : COLORS.deviceOffline);

  return (
    <div style={{ flex: 2, display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* 拓扑概览统计 */}
      <div style={{ display: 'flex', gap: 8 }}>
        {[
          { label: '站点', value: topology?.summary.total_stations || 0, icon: <EnvironmentOutlined />, color: COLORS.station },
          { label: '网关', value: topology?.summary.total_gateways || 0, icon: <ApiOutlined />, color: COLORS.gateway },
          { label: '设备', value: topology?.summary.total_devices || 0, icon: <DesktopOutlined />, color: COLORS.info },
          { label: '在线', value: topology?.summary.online_devices || 0, icon: <CheckCircleOutlined />, color: COLORS.success },
          { label: '故障', value: topology?.summary.fault_devices || 0, icon: <WarningOutlined />, color: COLORS.danger },
        ].map(item => (
          <div key={item.label} style={{
            flex: 1,
            background: COLORS.bgCard,
            border: `1px solid ${COLORS.border}`,
            borderRadius: 8,
            padding: '8px 12px',
            textAlign: 'center',
          }}>
            <div style={{ color: item.color, fontSize: 16, marginBottom: 2 }}>{item.icon}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: item.color }}>{item.value}</div>
            <div style={{ fontSize: 11, color: COLORS.textDim }}>{item.label}</div>
          </div>
        ))}
      </div>

      {/* 拓扑图 */}
      <div style={{
        flex: 1,
        background: COLORS.bgCard,
        border: `1px solid ${COLORS.border}`,
        borderRadius: 8,
        position: 'relative',
        overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute', top: 8, left: 12, zIndex: 10,
          fontSize: 14, fontWeight: 600, color: COLORS.accent,
        }}>
          <ThunderboltOutlined style={{ marginRight: 6 }} />实时拓扑
          <span title="复位缩放"
            onClick={() => setResetKey((k) => k + 1)}
            style={{ float: 'right', cursor: 'pointer', fontSize: 12, fontWeight: 400, color: COLORS.textDim, marginLeft: 8 }}>
            ⤢ 复位
          </span>
        </div>
        <ReactECharts
          key={resetKey}
          option={option}
          notMerge
          style={{ width: '100%', height: '100%' }}
          onEvents={{
            click: (params: { data?: TreeOpt }) => {
              const d = params?.data;
              handleNodeClick(d?.__raw, d?.id);
            },
          }}
        />

        {/* 点击详情浮卡 */}
        {detail && (
          <div style={{
            position: 'absolute', left: 12, bottom: 34, zIndex: 20,
            width: 260, padding: '10px 12px',
            background: 'rgba(6, 20, 40, 0.95)',
            border: `1px solid ${statusColor(detail)}`,
            borderRadius: 8,
            fontSize: 12, color: COLORS.text,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <b style={{ color: statusColor(detail) }}>{detail.name}</b>
              <CloseOutlined style={{ color: COLORS.textDim, cursor: 'pointer' }}
                onClick={() => { setDetail(null); onNodeClick(''); }} />
            </div>
            <div style={{ color: COLORS.textDim }}>
              {NODE_TYPE_TEXT[detail.type]} · {STATUS_TEXT[detail.status] || detail.status}
              {detail.device_type ? ` · ${detail.device_type}` : ''}
            </div>
            {detail.type === 'station' && detail.device_count != null && (
              <div style={{ marginTop: 4 }}>
                设备 {detail.device_count} · 在线 {detail.online_count ?? 0} · 故障 {detail.fault_count ?? 0}
              </div>
            )}
            {detail.health_score != null && (
              <div style={{ marginTop: 4 }}>健康度: {Math.round(detail.health_score)}</div>
            )}
            {nodeEvents.length > 0 && (
              <div style={{ marginTop: 8, borderTop: `1px solid ${COLORS.border}`, paddingTop: 6 }}>
                <div style={{ color: COLORS.textDim, marginBottom: 4 }}>最近事件</div>
                {nodeEvents.map((e) => (
                  <div key={e.id} style={{
                    color: e.type === 'alarm' ? COLORS.danger : COLORS.text,
                    marginBottom: 3, fontSize: 11,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }} title={e.title}>
                    · {e.title}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 图例 */}
        <div style={{
          position: 'absolute', bottom: 8, right: 12, zIndex: 10,
          display: 'flex', gap: 12, fontSize: 11, color: COLORS.textDim,
        }}>
          <span><span style={{ color: COLORS.station }}>●</span> 站点</span>
          <span><span style={{ color: COLORS.gateway }}>●</span> 网关</span>
          <span><span style={{ color: COLORS.success }}>●</span> 在线</span>
          <span><span style={{ color: COLORS.danger }}>●</span> 故障</span>
          <span><span style={{ color: COLORS.deviceOffline }}>●</span> 离线</span>
        </div>
      </div>
    </div>
  );
};

export default TopologyPanel;
