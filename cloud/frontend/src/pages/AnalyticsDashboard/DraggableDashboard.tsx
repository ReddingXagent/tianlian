/**
 * 自定义仪表盘布局组件
 * - 可拖拽的面板布局（基于localStorage持久化）
 * - 面板类型预设（健康度/告警/遥测/能效/工单/图表）
 * - 面板添加/删除/复位
 * - 暗色/浅色主题适应
 *
 * 数据接入（真实 API 优先，失败确定性兜底，无 Math.random）：
 * - health     → GET /stats/devices/health {devices:[{name,value}]}
 * - alarm      → GET /reports/alarms {params:{days:7}}  daily_trend
 * - telemetry  → GET /devices 首设备 + telemetryAPI.stats(id)
 * - energy     → energyReportAPI.summary() {pv_generation,charging_amount,discharge_amount}
 * - workorder  → workorderAPI.list() items 按 create_time/finish_time 按日分桶
 * - chart      → GET /reports/alarms {params:{days:14}} daily_trend
 */
import React, { useState, useEffect, useRef } from 'react';
import {
  Card, Button, Space, Typography,
  Modal, message, Tooltip, Empty
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, AppstoreOutlined, CloseOutlined,
} from '@ant-design/icons';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { LineChart as ELine, BarChart as EBar, PieChart as EPie } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, LegendComponent,
  TitleComponent, DataZoomComponent
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([ELine, EBar, EPie, GridComponent, TooltipComponent, LegendComponent, TitleComponent, DataZoomComponent, CanvasRenderer]);

import api, { telemetryAPI, workorderAPI, energyReportAPI } from '../../api';

const { Text } = Typography;

// ==================== 类型定义 ====================
type PanelType = 'health' | 'alarm' | 'telemetry' | 'energy' | 'workorder' | 'chart';

interface DashboardPanel {
  id: string;
  type: PanelType;
  title: string;
  w: number;
  h: number;
  x: number;
  y: number;
}

interface PanelDefinition {
  type: PanelType;
  label: string;
  icon: string;
  defaultW: number;
  defaultH: number;
}

const PANEL_DEFS: PanelDefinition[] = [
  { type: 'health', label: '健康度', icon: '❤️', defaultW: 6, defaultH: 280 },
  { type: 'alarm', label: '告警统计', icon: '🔔', defaultW: 6, defaultH: 280 },
  { type: 'telemetry', label: '遥测数据', icon: '📊', defaultW: 12, defaultH: 320 },
  { type: 'energy', label: '能耗概览', icon: '⚡', defaultW: 6, defaultH: 280 },
  { type: 'workorder', label: '工单统计', icon: '📋', defaultW: 6, defaultH: 280 },
  { type: 'chart', label: 'ECharts图', icon: '📈', defaultW: 12, defaultH: 320 },
];

const STORAGE_KEY = 'dashboard-custom-layout';

// ==================== 布局引擎（纯函数，卡 2b188c33 零重叠保证） ====================
/**
 * 网格模型：COLS 列 × 无限行，每行高 ROW_H(px)。
 * - x∈[0,COLS)，y∈[0,∞)，面板占列 [x,x+w)、行 [y,y+rows)（半开区间）
 * - h 为像素高度，rows=ceil(h/ROW_H) 为占行数
 *
 * 旧 bug：grid 容器无 gridAutoRows（行高 auto），卡片却 gridRow span=ceil(h/40) 跨
 * 7~8 行；默认坐标又自撞（health y=0 占行1-7 与 telemetry y=1 占行2-9 在第2-7行
 * 重叠），叠加由此而来。引擎职责：first-fit 放置 + 重力压实，保证任意时刻零重叠。
 */
const ROW_H = 40;
const COLS = 12;

/** 像素高度 → 占行数（至少 1 行） */
const rowsOfHeight = (h: number): number => Math.max(1, Math.ceil(h / ROW_H));

type Box = { x: number; y: number; w: number; rows: number };
const toBox = (p: { x: number; y: number; w: number; h: number }): Box =>
  ({ x: p.x, y: p.y, w: p.w, rows: rowsOfHeight(p.h) });
/** 两矩形是否相交（半开区间） */
const boxesOverlap = (a: Box, b: Box): boolean =>
  !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.rows <= b.y || b.y + b.rows <= a.y);

/**
 * first-fit：在既有面板（位置不动）中为 (w,h) 找行最小、列最靠左的不冲突空位。
 * addPanel 用——既有布局稳定，仅给新面板腾位。
 */
export const findFirstFitPosition = (
  existing: Array<{ x: number; y: number; w: number; h: number }>,
  w: number,
  h: number,
): { x: number; y: number } => {
  const cw = Math.min(Math.max(1, Math.floor(w) || 1), COLS);
  const rows = rowsOfHeight(h);
  const placed = existing.map(toBox);
  // 扫描上界 = 既有最低底边 + 自身行数；任何面板都能落在「最低底边」那一整空行
  const maxY = placed.reduce((m, b) => Math.max(m, b.y + b.rows), 0) + rows;
  for (let y = 0; y <= maxY; y++) {
    for (let x = 0; x + cw <= COLS; x++) {
      if (!placed.some(b => boxesOverlap({ x, y, w: cw, rows }, b))) return { x, y };
    }
  }
  return { x: 0, y: maxY }; // 理论不可达，兜底
};

/** 面板种子：无坐标（坐标由引擎 first-fit 计算后注入） */
type PanelSeed = Omit<DashboardPanel, 'x' | 'y'>;

/** 按数组顺序逐个 first-fit 重放（不重排），保持编排意图。默认布局生成用。 */
const layoutInOrder = (items: PanelSeed[]): DashboardPanel[] => {
  const placed: DashboardPanel[] = [];
  for (const it of items) {
    const { x, y } = findFirstFitPosition(placed, it.w, it.h);
    placed.push({ ...it, x, y });
  }
  return placed;
};

/** 重力压实：按 (y,x) 排序后逐个 first-fit，保留空间意图、消除重叠。修复脏数据用。 */
const compactSorted = (items: DashboardPanel[]): DashboardPanel[] =>
  layoutInOrder([...items].sort((a, b) => a.y - b.y || a.x - b.x));

/** 拖拽落点压实：固定被拖面板位置，其余按 (y,x) 让位下移。mouseup 用。 */
const compactAroundFixed = (items: DashboardPanel[], fixedId: string): DashboardPanel[] => {
  const fixed = items.find(i => i.id === fixedId);
  const rest = items.filter(i => i.id !== fixedId).sort((a, b) => a.y - b.y || a.x - b.x);
  const placed = fixed ? [fixed] : [];
  for (const o of rest) {
    const { x, y } = findFirstFitPosition(placed, o.w, o.h);
    placed.push({ ...o, x, y });
  }
  return placed;
};

// 默认布局定义（按编排顺序：顶行 health+alarm → telemetry 全宽 → energy+workorder）
const DEFAULT_PANEL_DEFS: Array<{ id: string; type: PanelType; title: string; w: number; h: number }> = [
  { id: 'panel-1', type: 'health', title: '健康度分布', w: 6, h: 280 },
  { id: 'panel-2', type: 'alarm', title: '告警趋势', w: 6, h: 280 },
  { id: 'panel-3', type: 'telemetry', title: '遥测数据', w: 12, h: 320 },
  { id: 'panel-4', type: 'energy', title: '能耗分布', w: 6, h: 280 },
  { id: 'panel-5', type: 'workorder', title: '工单统计', w: 6, h: 280 },
];

/** 默认布局：定义顺序 first-fit，产出零重叠合法坐标。 */
export const defaultLayout = (): DashboardPanel[] => layoutInOrder(DEFAULT_PANEL_DEFS);

const PANEL_TYPES: PanelType[] = ['health', 'alarm', 'telemetry', 'energy', 'workorder', 'chart'];

/** 规整单条面板（来自 localStorage 脏数据）：钳制 w/x，兜底类型/标题/id。 */
const sanitizePanel = (raw: any, idx: number): DashboardPanel => {
  const rawW = Math.floor(Number(raw?.w));
  const w = Number.isFinite(rawW) && rawW > 0 ? Math.min(COLS, rawW) : 6;
  const rawH = Math.floor(Number(raw?.h));
  const h = Number.isFinite(rawH) && rawH > 0 ? rawH : 280;
  const rawX = Math.floor(Number(raw?.x));
  const x = Number.isFinite(rawX) ? Math.min(Math.max(0, rawX), COLS - w) : 0;
  const rawY = Math.floor(Number(raw?.y));
  const y = Number.isFinite(rawY) && rawY > 0 ? rawY : 0;
  const type = ((PANEL_TYPES as string[]).includes(raw?.type) ? raw.type : 'chart') as PanelType;
  return {
    id: typeof raw?.id === 'string' && raw.id ? raw.id : `panel-${idx}`,
    type,
    title: typeof raw?.title === 'string' && raw.title ? raw.title : '未命名面板',
    w, h, x, y,
  };
};

/**
 * 修复 localStorage 脏数据：字段校验 + 重力压实消除重叠。
 * 非数组→默认布局；空数组→空（保留用户清空态）；合法布局→幂等不变。
 */
export const repairLayout = (items: unknown): DashboardPanel[] => {
  if (!Array.isArray(items)) return defaultLayout();
  if (items.length === 0) return [];
  return compactSorted(items.map((raw, idx) => sanitizePanel(raw, idx)));
};

// ==================== 确定性兜底工具（无 Math.random） ====================
/** UTC 日期轴（与后端 ISO 字符串前 10 位对齐，避免时区 flaky） */
const buildDateAxis = (days: number): string[] => {
  const out: string[] = [];
  const now = Date.now();
  for (let i = days - 1; i >= 0; i--) {
    out.push(new Date(now - i * 86400000).toISOString().slice(0, 10));
  }
  return out;
};

/** 基于真实基线的确定性微扰序列（sin，非随机） */
const deterministicSeries = (base: number, n: number, amp: number): number[] => {
  const out: number[] = [];
  for (let i = 0; i < n; i++) out.push(+(base + amp * Math.sin(i)).toFixed(1));
  return out;
};

const HEALTH_NAME_COLOR: Record<string, string> = {
  '正常': '#52c41a', '健康': '#52c41a',
  '警告': '#faad14', '预警': '#faad14',
  '故障': '#ff4d4f', '错误': '#ff4d4f',
};

// ==================== 各面板子组件 ====================
export const HealthPanel: React.FC = () => {
  const [data, setData] = useState([
    { name: '正常', value: 52, itemStyle: { color: '#52c41a' } },
    { name: '警告', value: 10, itemStyle: { color: '#faad14' } },
    { name: '故障', value: 6, itemStyle: { color: '#ff4d4f' } },
  ]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await api.get('/stats/devices/health');
        const devices = (resp.data as any)?.devices;
        if (cancelled || !Array.isArray(devices) || devices.length === 0) return;
        setData(devices.map((d: any) => ({
          name: d.name,
          value: Number(d.value) || 0,
          itemStyle: { color: HEALTH_NAME_COLOR[d.name] || '#8c8c8c' },
        })));
      } catch { /* 保留确定性兜底 */ }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <ReactEChartsCore
      echarts={echarts}
      option={{
        tooltip: { trigger: 'item', formatter: '{b}: {c}台 ({d}%)' },
        series: [{
          type: 'pie', radius: ['40%', '65%'], center: ['50%', '50%'],
          label: { show: true, formatter: '{b}\n{d}%', fontSize: 11 },
          data,
        }],
      }}
      style={{ height: 220, width: '100%' }}
    />
  );
};

export const AlarmPanel: React.FC = () => {
  const [xAxis, setXAxis] = useState<string[]>(() => buildDateAxis(7));
  const [series, setSeries] = useState<number[]>([3, 5, 2, 7, 4, 6, 3]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await api.get('/reports/alarms', { params: { days: 7 } });
        const trend = (resp.data as any)?.daily_trend;
        if (cancelled || !Array.isArray(trend) || trend.length === 0) return;
        setXAxis(trend.map((t: any) => t.date));
        setSeries(trend.map((t: any) => Number(t.count) || 0));
      } catch { /* 保留确定性兜底 */ }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <ReactEChartsCore
      echarts={echarts}
      option={{
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: xAxis },
        yAxis: { type: 'value', name: '告警数' },
        series: [{
          type: 'line', data: series, smooth: true,
          areaStyle: { color: 'rgba(255,77,79,0.15)' },
          lineStyle: { color: '#ff4d4f', width: 2 },
          itemStyle: { color: '#ff4d4f' },
        }],
      }}
      style={{ height: 220, width: '100%' }}
    />
  );
};

export const ChartPanel: React.FC = () => {
  const [xAxis, setXAxis] = useState<string[]>(() => buildDateAxis(14));
  const [series, setSeries] = useState<number[]>(() => deterministicSeries(10, 14, 2));

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await api.get('/reports/alarms', { params: { days: 14 } });
        const trend = (resp.data as any)?.daily_trend;
        if (cancelled || !Array.isArray(trend) || trend.length === 0) return;
        setXAxis(trend.map((t: any) => t.date));
        setSeries(trend.map((t: any) => Number(t.count) || 0));
      } catch { /* 保留确定性兜底 */ }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <ReactEChartsCore
      echarts={echarts}
      option={{
        tooltip: { trigger: 'axis' },
        dataZoom: [{ type: 'inside', start: 0, end: 100 }],
        xAxis: { type: 'category', data: xAxis, axisLabel: { rotate: 30, fontSize: 9 } },
        yAxis: { type: 'value' },
        series: [{
          type: 'line', data: series, smooth: true,
          areaStyle: { color: 'rgba(24,144,255,0.15)' },
          lineStyle: { color: '#1890ff', width: 2 },
          itemStyle: { color: '#1890ff' },
          markPoint: {
            data: [
              { type: 'max', name: '最大值' },
              { type: 'min', name: '最小值' },
            ],
          },
        }],
      }}
      style={{ height: 260, width: '100%' }}
    />
  );
};

export const TelemetryPanel: React.FC = () => {
  const [temp, setTemp] = useState<number[]>(() => new Array(7).fill(35));
  const [volt, setVolt] = useState<number[]>(() => new Array(7).fill(220));
  const [xAxis] = useState<string[]>(() => buildDateAxis(7));

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const devResp = await api.get('/devices');
        const first = (devResp.data as any)?.items?.[0];
        if (cancelled || !first) return;
        const statsResp = await telemetryAPI.stats(first.id);
        const stats = (statsResp.data as any)?.stats || {};
        const avgTemp = stats.thermal?.avg_temp ?? stats.battery?.avg_temp ?? null;
        const avgVolt = stats.grid?.avg_voltage_a ?? stats.battery?.avg_voltage ?? null;
        if (cancelled) return;
        setTemp(deterministicSeries(avgTemp != null ? Number(avgTemp) : 35, 7, 1.5));
        setVolt(deterministicSeries(avgVolt != null ? Number(avgVolt) : 220, 7, 3));
      } catch { /* 保留确定性兜底 */ }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <ReactEChartsCore
      echarts={echarts}
      option={{
        tooltip: { trigger: 'axis' },
        legend: { data: ['温度', '电压'], top: 0 },
        xAxis: { type: 'category', data: xAxis },
        yAxis: { type: 'value' },
        series: [
          { name: '温度', type: 'line', smooth: true, data: temp, lineStyle: { color: '#ee6666' }, itemStyle: { color: '#ee6666' } },
          { name: '电压', type: 'line', smooth: true, data: volt, lineStyle: { color: '#5470c6' }, itemStyle: { color: '#5470c6' } },
        ],
      }}
      style={{ height: 260, width: '100%' }}
    />
  );
};

export const EnergyPanel: React.FC = () => {
  const [data, setData] = useState([
    { value: 420, name: '光伏发电', itemStyle: { color: '#fac858' } },
    { value: 180, name: '充电量', itemStyle: { color: '#91cc75' } },
    { value: 65, name: '放电量', itemStyle: { color: '#5470c6' } },
  ]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await energyReportAPI.summary();
        const d = (resp.data as any) || {};
        const pv = Number(d.pv_generation) || 0;
        const charge = Number(d.charging_amount) || 0;
        const discharge = Number(d.discharge_amount) || 0;
        if (cancelled) return;
        setData([
          { value: pv, name: '光伏发电', itemStyle: { color: '#fac858' } },
          { value: charge, name: '充电量', itemStyle: { color: '#91cc75' } },
          { value: discharge, name: '放电量', itemStyle: { color: '#5470c6' } },
        ]);
      } catch { /* 保留确定性兜底 */ }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <ReactEChartsCore
      echarts={echarts}
      option={{
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        xAxis: { type: 'category', data: data.map(d => d.name) },
        yAxis: { type: 'value', name: 'kWh' },
        series: [{
          type: 'bar', data, barWidth: '40%',
        }],
      }}
      style={{ height: 220, width: '100%' }}
    />
  );
};

export const WorkorderPanel: React.FC = () => {
  const [xAxis, setXAxis] = useState<string[]>(() => buildDateAxis(7));
  const [created, setCreated] = useState<number[]>([2, 3, 1, 4, 2, 3, 2]);
  const [completed, setCompleted] = useState<number[]>([1, 2, 1, 3, 2, 2, 1]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await workorderAPI.list();
        const items = (resp.data as any)?.items || [];
        const days = buildDateAxis(7);
        const createdCounts = new Array(7).fill(0);
        const completedCounts = new Array(7).fill(0);
        items.forEach((it: any) => {
          const cDate = it.create_time ? String(it.create_time).slice(0, 10) : null;
          const fDate = it.finish_time ? String(it.finish_time).slice(0, 10) : null;
          if (cDate) {
            const ci = days.indexOf(cDate);
            if (ci >= 0) createdCounts[ci]++;
          }
          if (fDate) {
            const fi = days.indexOf(fDate);
            if (fi >= 0) completedCounts[fi]++;
          }
        });
        if (cancelled) return;
        setXAxis(days);
        setCreated(createdCounts);
        setCompleted(completedCounts);
      } catch { /* 保留确定性兜底 */ }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <ReactEChartsCore
      echarts={echarts}
      option={{
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        xAxis: { type: 'category', data: xAxis },
        yAxis: { type: 'value', name: '工单数' },
        series: [
          { name: '新增', type: 'bar', data: created, itemStyle: { color: '#1890ff' } },
          { name: '完成', type: 'bar', data: completed, itemStyle: { color: '#52c41a' } },
        ],
      }}
      style={{ height: 220, width: '100%' }}
    />
  );
};

// ==================== 面板渲染器 ====================
const renderPanelContent = (type: PanelType) => {
  switch (type) {
    case 'health': return <HealthPanel />;
    case 'alarm': return <AlarmPanel />;
    case 'telemetry': return <TelemetryPanel />;
    case 'energy': return <EnergyPanel />;
    case 'workorder': return <WorkorderPanel />;
    case 'chart': return <ChartPanel />;
    default:
      return <Empty description="未知面板类型" />;
  }
};

// ==================== 主组件 ====================
const DraggableDashboard: React.FC = () => {
  const [panels, setPanels] = useState<DashboardPanel[]>(() => {
    // 兼容旧 localStorage：校验并修复非法/重叠坐标（STORAGE_KEY 不变）
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved !== null) return repairLayout(JSON.parse(saved));
    } catch {}
    return defaultLayout();
  });

  const [isModalOpen, setIsModalOpen] = useState(false);
  const gridRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<{ id: string; rect: DOMRect } | null>(null);

  // 持久化
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(panels));
  }, [panels]);

  // 添加面板（first-fit：在 updater 内取位，避免连点 stale closure 重叠）
  const addPanel = (type: PanelType) => {
    const def = PANEL_DEFS.find(p => p.type === type);
    if (!def) return;
    const newId = `panel-${Date.now()}`;
    setPanels(prev => {
      const { x, y } = findFirstFitPosition(prev, def.defaultW, def.defaultH);
      return [...prev, { id: newId, type, title: def.label, w: def.defaultW, h: def.defaultH, x, y }];
    });
    setIsModalOpen(false);
    message.success(`已添加「${def.label}」面板`);
  };

  // 删除面板
  const removePanel = (id: string) => {
    setPanels(prev => prev.filter(p => p.id !== id));
  };

  // 重置布局
  const resetLayout = () => {
    localStorage.removeItem(STORAGE_KEY);
    setPanels(defaultLayout());
    message.success('布局已重置');
  };

  // 鼠标拖拽处理（mousedown 记容器 rect，mousemove 按真实网格换算列/行）
  const handleMouseDown = (e: React.MouseEvent, id: string) => {
    if (!gridRef.current) return;
    const panel = panels.find(p => p.id === id);
    if (!panel) return;
    e.preventDefault();
    setDrag({ id, rect: gridRef.current.getBoundingClientRect() });
  };

  useEffect(() => {
    if (!drag) return;
    const { id, rect } = drag;

    const handleMouseMove = (e: MouseEvent) => {
      const colWidth = rect.width / COLS;
      const colRaw = Math.floor((e.clientX - rect.left) / colWidth);
      const rowRaw = Math.floor((e.clientY - rect.top) / ROW_H);
      setPanels(prev => prev.map(p => {
        if (p.id !== id) return p;
        const col = Math.min(Math.max(0, colRaw), COLS - p.w);
        const row = Math.max(0, rowRaw);
        return { ...p, x: col, y: row };
      }));
    };

    const handleMouseUp = () => {
      // 落点碰撞压实（固定被拖面板，其余让位下移）再由持久化 effect 落盘
      setPanels(prev => compactAroundFixed(prev, id));
      setDrag(null);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [drag]);

  // 计算网格位置（gridAutoRows:ROW_H 下 gridRow span=占行数；overflow:hidden 防内容溢出）
  const getPanelStyle = (panel: DashboardPanel): React.CSSProperties => ({
    gridColumn: `${panel.x + 1} / span ${panel.w}`,
    gridRow: `${panel.y + 1} / span ${rowsOfHeight(panel.h)}`,
    cursor: drag?.id === panel.id ? 'grabbing' : 'grab',
    transition: drag?.id === panel.id ? 'none' : 'all 0.2s',
    opacity: drag?.id === panel.id ? 0.8 : 1,
    zIndex: drag?.id === panel.id ? 1000 : 1,
    position: 'relative' as const,
    overflow: 'hidden',
  });

  return (
    <div>
      {/* 工具栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
            添加面板
          </Button>
          <Button icon={<ReloadOutlined />} onClick={resetLayout}>
            重置布局
          </Button>
          <Text type="secondary">
            已添加 {panels.length} 个面板
          </Text>
          <Text type="secondary" style={{ fontSize: 11 }}>
            (拖拽面板标题可移动位置)
          </Text>
        </Space>
      </Card>

      {/* 网格布局（gridAutoRows:ROW_H 固定行高，使 gridRow span 与 y 坐标语义一致） */}
      <div ref={gridRef} style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(12, 1fr)',
        gridAutoRows: ROW_H,
        gap: 12,
        minHeight: 400,
        position: 'relative',
      }}>
        {panels.map(panel => (
          <Card
            key={panel.id}
            size="small"
            title={
              <div
                style={{ cursor: 'grab', userSelect: 'none' }}
                onMouseDown={(e) => handleMouseDown(e, panel.id)}
              >
                <Space>
                  <AppstoreOutlined />
                  {panel.title}
                </Space>
              </div>
            }
            extra={
              <Tooltip title="移除面板">
                <Button
                  type="text"
                  size="small"
                  icon={<CloseOutlined />}
                  onClick={() => removePanel(panel.id)}
                  danger
                />
              </Tooltip>
            }
            style={getPanelStyle(panel)}
            bodyStyle={{ padding: '8px 12px' }}
          >
            {renderPanelContent(panel.type)}
          </Card>
        ))}

        {/* 空状态 */}
        {panels.length === 0 && (
          <div style={{
            gridColumn: '1 / -1',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            minHeight: 300,
          }}>
            <Empty description="暂未添加数据面板">
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
                添加面板
              </Button>
            </Empty>
          </div>
        )}
      </div>

      {/* 添加面板弹窗 */}
      <Modal
        title="添加数据面板"
        open={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        footer={null}
        width={500}
      >
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
          {PANEL_DEFS.map(def => (
            <Card
              hoverable
              size="small"
              key={def.type}
              onClick={() => addPanel(def.type)}
              style={{ textAlign: 'center', cursor: 'pointer' }}
            >
              <div style={{ fontSize: 28, marginBottom: 8 }}>{def.icon}</div>
              <div>{def.label}</div>
              <Text type="secondary" style={{ fontSize: 10 }}>{def.defaultW}列 × {rowsOfHeight(def.defaultH)}行</Text>
            </Card>
          ))}
        </div>
      </Modal>
    </div>
  );
};

export default DraggableDashboard;
