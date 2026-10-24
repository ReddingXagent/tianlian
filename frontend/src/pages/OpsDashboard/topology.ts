/**
 * 拓扑图 Canvas 渲染
 *
 * 站点(上) → 网关(中) → 设备(下) 三层层级布局，含选中/故障发光、点击位置存储。
 */
import type { TopologyData, TopologyNode, NodePosition } from './types';
import { COLORS, STATUS_COLORS, TOPOLOGY_STYLES } from './constants';

export function renderTopology(
  canvas: HTMLCanvasElement,
  data: TopologyData,
  selectedNode: string | null,
  onNodeClick: (id: string) => void,
) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  // 尺寸以 CSS 布局尺寸为准（style 100% 由容器决定），DPR 只作用于 backing store，
  // 用 setTransform 避免重复渲染时 scale 叠乘导致画布指数膨胀/溢出（卡 fcfd13fd）
  const W = canvas.clientWidth;
  const H = canvas.clientHeight;
  const dpr = window.devicePixelRatio || 1;
  if (W <= 0 || H <= 0) return;

  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  // 清空
  ctx.fillStyle = COLORS.bg;
  ctx.fillRect(0, 0, W, H);

  // 收集所有节点
  const allNodes = [
    ...data.nodes.stations,
    ...data.nodes.gateways,
    ...data.nodes.devices,
  ];

  // 计算布局：站点在上方，网关在中间，设备在下方
  const positions: NodePosition[] = [];
  const stationCount = data.nodes.stations.length;
  const gatewayCount = data.nodes.gateways.length;
  const deviceCount = data.nodes.devices.length;

  // 三层 Y 位置随画布高度自适应（1366x768 下不越界，卡 fcfd13fd）
  const stationY = Math.max(48, H * 0.16);
  const gatewayY = stationY + Math.max(90, H * 0.28);
  const deviceY = gatewayY + Math.max(80, H * 0.24);

  // 站点布局
  const stationSpacing = Math.min(200, (W - 100) / Math.max(stationCount, 1));
  const stationStartX = (W - stationSpacing * (stationCount - 1)) / 2;

  data.nodes.stations.forEach((s, i) => {
    const style = TOPOLOGY_STYLES.station;
    const statusColor = STATUS_COLORS[s.status] || style.color;
    positions.push({
      x: stationStartX + i * stationSpacing,
      y: stationY,
      node: { ...s, status: s.status },
      radius: style.radius,
    });
  });

  // 网关布局 - 挂在对应站点下方
  const gatewaysByStation: Record<number, TopologyNode[]> = {};
  data.nodes.gateways.forEach(g => {
    const sid = g.station_id || 0;
    if (!gatewaysByStation[sid]) gatewaysByStation[sid] = [];
    gatewaysByStation[sid].push(g);
  });

  Object.entries(gatewaysByStation).forEach(([sid, gateways]) => {
    const stationPos = positions.find(p => p.node.id === `station-${sid}`);
    const baseX = stationPos ? stationPos.x : W / 2;
    const gwSpacing = Math.min(80, 300 / Math.max(gateways.length, 1));
    const gwStartX = baseX - (gwSpacing * (gateways.length - 1)) / 2;

    gateways.forEach((g, i) => {
      positions.push({
        x: gwStartX + i * gwSpacing,
        y: gatewayY,
        node: g,
        radius: TOPOLOGY_STYLES.gateway.radius,
      });
    });
  });

  // 设备布局 - 挂在对应网关下方，超出单行则换行，避免节点重叠（卡 fcfd13fd）
  const devicesByGateway: Record<string, TopologyNode[]> = {};
  const orphanDevices: TopologyNode[] = [];

  data.nodes.devices.forEach(d => {
    if (d.gateway_id) {
      const key = `gateway-${d.gateway_id}`;
      if (!devicesByGateway[key]) devicesByGateway[key] = [];
      devicesByGateway[key].push(d);
    } else {
      orphanDevices.push(d);
    }
  });

  const deviceRowH = 42;
  Object.entries(devicesByGateway).forEach(([gid, devs]) => {
    const gwPos = positions.find(p => p.node.id === gid);
    const baseX = gwPos ? gwPos.x : W / 2;
    // 每行最多 5 个，行间距 42px；单行内间距固定 40px，不再随数量压缩到重叠
    const perRow = Math.max(1, Math.min(5, Math.floor((W - 40) / 40) || 1));
    devs.forEach((d, i) => {
      const rowLen = Math.min(perRow, devs.length - Math.floor(i / perRow) * perRow);
      const col = i % perRow;
      const x = baseX + (col - (rowLen - 1) / 2) * 40;
      const row = Math.floor(i / perRow);
      positions.push({
        x,
        y: deviceY + row * deviceRowH,
        node: d,
        radius: TOPOLOGY_STYLES.device.radius,
      });
    });
  });

  // 孤儿设备（无网关）统一铺在底部一行，避免覆盖网关层
  if (orphanDevices.length) {
    const perRow = Math.max(1, Math.min(Math.floor((W - 40) / 40), orphanDevices.length));
    orphanDevices.forEach((d, i) => {
      const rowLen = Math.min(perRow, orphanDevices.length - Math.floor(i / perRow) * perRow);
      const col = i % perRow;
      const x = W / 2 + (col - (rowLen - 1) / 2) * 40;
      const row = Math.floor(i / perRow);
      positions.push({
        x,
        y: deviceY + row * deviceRowH,
        node: d,
        radius: TOPOLOGY_STYLES.device.radius,
      });
    });
  }

  // 绘制连接线
  ctx.lineWidth = 1.5;
  data.edges.forEach(edge => {
    const sourcePos = positions.find(p => p.node.id === edge.source);
    const targetPos = positions.find(p => p.node.id === edge.target);
    if (!sourcePos || !targetPos) return;

    const isActive = selectedNode === edge.source || selectedNode === edge.target;
    ctx.strokeStyle = isActive ? COLORS.accent : 'rgba(32, 160, 255, 0.2)';
    ctx.lineWidth = isActive ? 2 : 1;

    ctx.beginPath();
    ctx.moveTo(sourcePos.x, sourcePos.y + sourcePos.radius);
    // 贝塞尔曲线
    const midY = (sourcePos.y + targetPos.y) / 2;
    ctx.bezierCurveTo(sourcePos.x, midY, targetPos.x, midY, targetPos.x, targetPos.y - targetPos.radius);
    ctx.stroke();
  });

  // 绘制节点
  positions.forEach(pos => {
    const { x, y, node, radius } = pos;
    const style = TOPOLOGY_STYLES[node.type] || TOPOLOGY_STYLES.device;
    const isSelected = selectedNode === node.id;
    const nodeColor = node.type === 'device'
      ? (STATUS_COLORS[node.status] || COLORS.deviceOffline)
      : (STATUS_COLORS[node.status] || style.color);

    // 发光效果
    if (isSelected || node.status === 'fault') {
      const glowColor = node.status === 'fault' ? 'rgba(245, 34, 45, 0.3)' : 'rgba(32, 160, 255, 0.3)';
      const gradient = ctx.createRadialGradient(x, y, radius, x, y, radius * 2);
      gradient.addColorStop(0, glowColor);
      gradient.addColorStop(1, 'transparent');
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(x, y, radius * 2, 0, Math.PI * 2);
      ctx.fill();
    }

    // 外圈
    ctx.strokeStyle = isSelected ? '#fff' : nodeColor;
    ctx.lineWidth = isSelected ? 3 : 2;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.stroke();

    // 内填充
    ctx.fillStyle = `${nodeColor}33`;
    ctx.fill();

    // 名称
    ctx.fillStyle = COLORS.text;
    ctx.font = `${node.type === 'station' ? 12 : 10}px sans-serif`;
    ctx.textAlign = 'center';
    const displayName = node.name.length > 6 ? node.name.slice(0, 6) + '..' : node.name;
    ctx.fillText(displayName, x, y + radius + 14);
  });

  // 存储位置信息到canvas用于点击检测
  (canvas as any).__positions = positions;
}
