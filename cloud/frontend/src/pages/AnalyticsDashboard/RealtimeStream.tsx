/**
 * 实时数据流可视化组件
 * - WebSocket实时数据流展示
 * - 多指标实时更新图表
 * - 数据流时间轴
 * - 自动滚动 & 动态更新
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Row, Col, Card, Select, Tag, Space, Button, Switch, message,
  Statistic, Typography, Badge, Tooltip, Empty, Spin, Alert
} from 'antd';
import {
  ReloadOutlined, PauseCircleOutlined, PlayCircleOutlined,
  ThunderboltOutlined, ApiOutlined, DownloadOutlined,
  LineChartOutlined, DotChartOutlined
} from '@ant-design/icons';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { LineChart as ELine, BarChart as EBar } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, LegendComponent,
  TitleComponent, DataZoomComponent
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([ELine, EBar, GridComponent, TooltipComponent, LegendComponent, TitleComponent, DataZoomComponent, CanvasRenderer]);

import { telemetryAPI } from '../../api';
import { useWebSocket } from '../../hooks/useWebSocket';
import { WS_ENDPOINTS } from '../../config/websocket';
import dayjs from 'dayjs';
import { deterministicValue, clampFinite } from './deterministic';

const { Text, Title: Txt } = Typography;

interface MetricPoint {
  timestamp: string;
  value: number;
}

interface MetricStream {
  key: string;
  label: string;
  unit: string;
  color: string;
  data: MetricPoint[];
  currentValue: number;
  min: number;
  max: number;
  avg: number;
}

const defaultMetrics: MetricStream[] = [
  { key: 'temperature', label: '温度', unit: '°C', color: '#ee6666', data: [], currentValue: 0, min: Infinity, max: -Infinity, avg: 0 },
  { key: 'voltage', label: '电压', unit: 'V', color: '#5470c6', data: [], currentValue: 0, min: Infinity, max: -Infinity, avg: 0 },
  { key: 'current', label: '电流', unit: 'A', color: '#91cc75', data: [], currentValue: 0, min: Infinity, max: -Infinity, avg: 0 },
  { key: 'power', label: '功率', unit: 'kW', color: '#fac858', data: [], currentValue: 0, min: Infinity, max: -Infinity, avg: 0 },
];

const MAX_POINTS = 60; // 最多显示60个数据点

// 确定性兜底基线（后端 stats 无电流字段；latest 无温度/电压）
const FALLBACK_BASELINE = { temperature: 35, voltage: 220, current: 12.5, power: 3 };
const POINT_INTERVAL_MS = 1000;   // 数据点生成间隔
const LATEST_POLL_MS = 5000;      // latest 轮询间隔

// 从 telemetryAPI.stats 提取真实基线，缺失字段降级为确定性兜底常量
const extractBaselines = (stats: any) => {
  const s = stats || {};
  return {
    temperature: clampFinite(s.thermal?.avg_temp ?? s.thermal?.avg_internal_temp ?? s.battery?.avg_temp, FALLBACK_BASELINE.temperature),
    voltage: clampFinite(s.grid?.avg_voltage_a, FALLBACK_BASELINE.voltage),
    current: FALLBACK_BASELINE.current,
    power: clampFinite(s.grid?.avg_power ?? s.battery?.avg_power ?? s.charger?.avg_power ?? s.pv?.avg_power, FALLBACK_BASELINE.power),
  };
};
type Baselines = ReturnType<typeof extractBaselines>;

// 各指标的确定性微扰振幅
const METRIC_AMP: Record<string, number> = {
  temperature: 2, voltage: 3, current: 2, power: 0.5,
};

const RealtimeStream: React.FC = () => {
  const [devices, setDevices] = useState<any[]>([]);
  const [deviceError, setDeviceError] = useState<string | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<number | null>(null);
  const [metrics, setMetrics] = useState<MetricStream[]>(defaultMetrics);
  const [isPaused, setIsPaused] = useState(false);
  const [loading, setLoading] = useState(false);
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>(['temperature', 'voltage', 'current', 'power']);
  const [baselines, setBaselines] = useState<Baselines>(FALLBACK_BASELINE);

  // ref 保存最新基线 / WS·轮询推送的真实值，供 interval 闭包读取（避免重启定时器）
  const baselinesRef = useRef<Baselines>(FALLBACK_BASELINE);
  const latestValuesRef = useRef<Record<string, number | null>>({});
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => { baselinesRef.current = baselines; }, [baselines]);

  // WebSocket连接
  const { isConnected, lastMessage } = useWebSocket({
    endpoint: WS_ENDPOINTS.dashboard,
    autoConnect: true,
  });

  // 加载设备列表
  useEffect(() => {
    loadDevices();
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // WS 推送遥测数值时缓存为该 tick 的真实值（dashboard 频道通常只推状态，数值流视后端而定）
  useEffect(() => {
    if (!lastMessage) return;
    const p = lastMessage.payload || {};
    const picked: Record<string, number> = {};
    ['temperature', 'voltage', 'current', 'power'].forEach(k => {
      if (typeof p[k] === 'number') picked[k] = p[k];
    });
    if (Object.keys(picked).length > 0) {
      latestValuesRef.current = { ...latestValuesRef.current, ...picked };
    }
  }, [lastMessage]);

  // 选中设备后：拉真实基线 + 轮询 latest 真实功率 + 生成确定性数据点（无 Math.random）
  useEffect(() => {
    if (!selectedDevice) return;
    // 真实基线（温度/电压/功率均值）；失败保留确定性兜底
    telemetryAPI.stats(selectedDevice).then(res => setBaselines(extractBaselines(res.data?.data?.stats))).catch(() => { /* 保留确定性兜底 */ });

    if (isPaused) return;
    intervalRef.current = setInterval(appendDataPoint, POINT_INTERVAL_MS);
    // latest 轮询：仅有功率类字段（grid_power_total/charger_power），失败忽略走基线兜底
    const pollLatest = async () => {
      try {
        const res = await telemetryAPI.latest(selectedDevice);
        const d = res.data?.data || {};
        const power = d.grid_power_total ?? d.charger_power ?? null;
        if (typeof power === 'number') {
          latestValuesRef.current = { ...latestValuesRef.current, power };
        }
      } catch {
        // 轮询失败忽略，基线兜底
      }
    };
    pollRef.current = setInterval(pollLatest, LATEST_POLL_MS);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [selectedDevice, isPaused]);

  const loadDevices = async () => {
    try {
      setDeviceError(null);
      const { default: api } = await import('../../api');
      const res = await api.get('/devices');
      const items = res.data?.data?.items ?? res.data?.items ?? [];
      setDevices(items);
      if (items.length > 0) setSelectedDevice(items[0].id);
    } catch (e: any) {
      setDevices([]);
      const text = e?.response?.data?.message || e?.response?.data?.detail || e?.message || '加载失败';
      setDeviceError(text);
      message.error('设备列表加载失败：' + text);
    }
  };

  // 追加一个数据点：优先用 WS/轮询推送的真实值，否则基于真实基线的确定性 sin（无 Math.random）
  const appendDataPoint = () => {
    const now = dayjs().format('HH:mm:ss');
    const t = Math.floor(Date.now() / 1000);
    const base = baselinesRef.current;
    const latest = latestValuesRef.current;

    setMetrics(prev =>
      prev.map(m => {
        const real = latest[m.key];
        const value = typeof real === 'number'
          ? +real.toFixed(2)
          : deterministicValue((base as any)[m.key] ?? 0, t, METRIC_AMP[m.key] ?? 1);

        const newPoint = { timestamp: now, value };
        const newData = [...m.data, newPoint].slice(-MAX_POINTS);
        const values = newData.map(d => d.value);
        const min = Math.min(...values);
        const max = Math.max(...values);
        const avg = +(values.reduce((a, b) => a + b, 0) / values.length).toFixed(1);

        return {
          ...m,
          data: newData,
          currentValue: value,
          min: Math.min(m.min === Infinity ? value : m.min, value),
          max: Math.max(m.max === -Infinity ? value : m.max, value),
          avg,
        };
      })
    );
  };

  const toggleMetric = (key: string) => {
    setSelectedMetrics(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    );
  };

  const resetData = () => {
    setMetrics(defaultMetrics.map(m => ({
      ...m,
      data: [],
      currentValue: 0,
      min: Infinity,
      max: -Infinity,
      avg: 0,
    })));
    message.success('数据已重置');
  };

  const handleExport = () => {
    const dataStr = JSON.stringify(metrics, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `realtime-stream-${dayjs().format('YYYYMMDD-HHmmss')}.json`;
    a.click();
    URL.revokeObjectURL(url);
    message.success('数据导出成功');
  };

  // 生成图表配置
  const getStreamChartOption = () => {
    const visibleMetrics = metrics.filter(m => selectedMetrics.includes(m.key));
    if (visibleMetrics.length === 0) return {};

    const firstMetric = visibleMetrics[0];
    const times = firstMetric.data.map(d => d.timestamp);

    const series = visibleMetrics.map(m => ({
      name: `${m.label} (${m.unit})`,
      type: 'line' as const,
      smooth: true,
      showSymbol: false,
      data: m.data.map(d => d.value),
      itemStyle: { color: m.color },
      lineStyle: { width: 2 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: m.color + '40' },
          { offset: 1, color: m.color + '05' },
        ]),
      },
    }));

    return {
      title: {
        text: '实时数据流',
        left: 'center',
        textStyle: { fontSize: 14, color: '#1890ff' },
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        backgroundColor: 'rgba(255,255,255,0.95)',
        borderColor: '#e8e8e8',
        borderWidth: 1,
      },
      legend: {
        data: visibleMetrics.map(m => `${m.label} (${m.unit})`),
        top: 30,
        type: 'scroll',
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        top: '22%',
        containLabel: true,
      },
      dataZoom: [
        { type: 'inside', start: 0, end: 100 },
      ],
      xAxis: {
        type: 'category' as const,
        data: times,
        boundaryGap: false,
        axisLine: { lineStyle: { color: '#e8e8e8' } },
        axisLabel: { color: '#666', fontSize: 10 },
      },
      yAxis: {
        type: 'value' as const,
        name: '',
        axisLine: { show: false },
        splitLine: { lineStyle: { type: 'dashed', color: '#f0f0f0' } },
      },
      series,
      animationDuration: 300,
    };
  };

  const currentMetrics = metrics.filter(m => selectedMetrics.includes(m.key));

  return (
    <div>
      <Row gutter={[16, 16]}>
        {/* 控制栏 */}
        <Col span={24}>
          <Card size="small">
            {deviceError && (
              <Alert type="error" showIcon style={{ marginBottom: 12 }}
                message="设备列表加载失败" description={deviceError}
                action={<Button size="small" icon={<ReloadOutlined />} onClick={loadDevices}>重试</Button>} />
            )}
            <Space wrap>
              <Select
                style={{ width: 200 }}
                placeholder="选择设备"
                value={selectedDevice}
                onChange={setSelectedDevice}
                options={devices.map(d => ({ label: d.name, value: d.id }))}
              />
              <Badge status={isConnected ? "success" : "error"} text={isConnected ? "已连接" : "未连接"} />
              <Tag color={isPaused ? 'orange' : 'green'}>{isPaused ? '已暂停' : '实时更新中'}</Tag>
              <Tooltip title={isPaused ? '继续' : '暂停'}>
                <Button
                  icon={isPaused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
                  onClick={() => setIsPaused(!isPaused)}
                  type={isPaused ? 'primary' : 'default'}
                  danger={isPaused}
                />
              </Tooltip>
              <Button icon={<ReloadOutlined />} onClick={resetData}>重置</Button>
              <Button icon={<DownloadOutlined />} onClick={handleExport}>导出</Button>
            </Space>
          </Card>
        </Col>

        {/* 指标开关 */}
        <Col span={24}>
          <Card size="small" title="指标选择">
            <Space wrap>
              {metrics.map(m => (
                <Tag
                  key={m.key}
                  color={selectedMetrics.includes(m.key) ? m.color : undefined}
                  style={{ cursor: 'pointer', userSelect: 'none' }}
                  onClick={() => toggleMetric(m.key)}
                >
                  {selectedMetrics.includes(m.key) ? '✓ ' : '○ '}
                  {m.label} ({m.unit})
                </Tag>
              ))}
            </Space>
          </Card>
        </Col>

        {/* 实时数值展示 */}
        {currentMetrics.map(m => (
          <Col xs={12} sm={6} key={m.key}>
            <Card size="small" hoverable>
              <Statistic
                title={
                  <Space>
                    <Badge color={m.color} />
                    {m.label}
                  </Space>
                }
                value={m.currentValue}
                suffix={m.unit}
                precision={1}
                valueStyle={{
                  color: m.color,
                  fontSize: 24,
                  fontWeight: 'bold',
                  transition: 'color 0.3s',
                }}
                prefix={m.key === 'temperature' ? <ThunderboltOutlined /> : <ApiOutlined />}
              />
              <div style={{ marginTop: 8 }}>
                <Space size={12}>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    最小: {m.min === Infinity ? '-' : m.min.toFixed(1)}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    最大: {m.max === -Infinity ? '-' : m.max.toFixed(1)}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    平均: {m.avg}
                  </Text>
                </Space>
              </div>
            </Card>
          </Col>
        ))}

        {/* 实时流图表 */}
        <Col span={24}>
          <Card>
            {metrics[0].data.length > 0 ? (
              <ReactEChartsCore
                echarts={echarts}
                option={getStreamChartOption()}
                style={{ width: '100%', height: 400 }}
                opts={{ renderer: 'svg' }}
                notMerge={false}
              />
            ) : (
              <Empty description="等待实时数据..." style={{ padding: 60 }}>
                <Button type="primary" onClick={() => setIsPaused(false)}>
                  开始接收数据
                </Button>
              </Empty>
            )}
          </Card>
        </Col>

        {/* 数据点表格 */}
        {metrics[0].data.length > 0 && (
          <Col span={24}>
            <Card
              title="最新数据点"
              extra={<Text type="secondary">显示最近 {MAX_POINTS} 条记录</Text>}
              size="small"
            >
              <div style={{ maxHeight: 200, overflow: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ background: '#fafafa' }}>
                      <th style={thStyle}>时间</th>
                      {currentMetrics.map(m => (
                        <th key={m.key} style={{ ...thStyle, color: m.color }}>{m.label}({m.unit})</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {metrics[0].data.slice(-20).reverse().map((pt, idx) => (
                      <tr key={idx}>
                        <td style={tdStyle}>{pt.timestamp}</td>
                        {currentMetrics.map(m => {
                          const dp = m.data.find(d => d.timestamp === pt.timestamp);
                          return <td key={m.key} style={tdStyle}>{dp?.value.toFixed(1) ?? '-'}</td>;
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </Col>
        )}
      </Row>
    </div>
  );
};

const thStyle: React.CSSProperties = {
  padding: '6px 12px',
  textAlign: 'left',
  borderBottom: '2px solid #f0f0f0',
  fontWeight: 600,
};

const tdStyle: React.CSSProperties = {
  padding: '4px 12px',
  borderBottom: '1px solid #f0f0f0',
  fontFamily: 'monospace',
};

export default RealtimeStream;