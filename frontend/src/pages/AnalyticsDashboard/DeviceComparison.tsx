/**
 * 多设备对比视图组件
 * - 多设备指标并排对比
 * - 雷达图/柱状图对比模式
 * - 指标差异高亮
 * - 一键导出对比报告
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Row, Col, Card, Select, Tag, Space, Button, Statistic,
  Table, message, Empty, Tooltip, Typography, Spin, Divider
} from 'antd';
import {
  ReloadOutlined, DownloadOutlined, RadarChartOutlined,
  BarChartOutlined, SwapOutlined, ThunderboltOutlined
} from '@ant-design/icons';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { RadarChart, BarChart as EBar } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, LegendComponent,
  TitleComponent, PolarComponent
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([RadarChart, EBar, GridComponent, TooltipComponent, LegendComponent, TitleComponent, PolarComponent, CanvasRenderer]);

import api, { efficiencyAPI, telemetryAPI } from '../../api';
import dayjs from 'dayjs';

const { Text } = Typography;

interface DeviceMetric {
  label: string;
  key: string;
  unit: string;
  value: number;
  maxValue?: number;
  color?: string;
}

interface DeviceCompareData {
  deviceId: number;
  deviceName: string;
  metrics: DeviceMetric[];
  healthScore: number;
  status: string;
}

const defaultMetricDefs: DeviceMetric[] = [
  { label: '温度', key: 'temperature', unit: '°C', value: 0, maxValue: 100, color: '#ee6666' },
  { label: '电压', key: 'voltage', unit: 'V', value: 0, maxValue: 380, color: '#5470c6' },
  { label: '电流', key: 'current', unit: 'A', value: 0, maxValue: 100, color: '#91cc75' },
  { label: '功率', key: 'power', unit: 'kW', value: 0, maxValue: 50, color: '#fac858' },
  { label: '健康度', key: 'health', unit: '分', value: 0, maxValue: 100, color: '#73c0de' },
];

const DeviceComparison: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [allDevices, setAllDevices] = useState<any[]>([]);
  const [selectedDevices, setSelectedDevices] = useState<number[]>([]);
  const [compareData, setCompareData] = useState<DeviceCompareData[]>([]);
  const [chartMode, setChartMode] = useState<'radar' | 'bar'>('radar');

  useEffect(() => {
    loadDevices();
  }, []);

  const loadDevices = async () => {
    try {
      const res = await api.get('/devices');
      const items = res.data?.data?.items ?? res.data?.items ?? [];
      setAllDevices(items);
    } catch {
      setAllDevices([
        { id: 1, name: '光伏逆变器-001' },
        { id: 2, name: '储能PCS-001' },
        { id: 3, name: '充电桩-001' },
        { id: 4, name: '智能电表-001' },
        { id: 5, name: '光伏逆变器-002' },
      ]);
    }
  };

  // 单设备真实指标：健康度←efficiency，温度/电压/功率←stats，电流后端无统计→P/U 物理推导或 0
  // 任一请求失败该字段降级为确定性兜底（0 / 在线派生健康度），全程无 Math.random
  const loadDeviceCompare = async (id: number): Promise<DeviceCompareData> => {
    const device = allDevices.find(d => d.id === id);
    const deviceName = device?.name || `设备${id}`;
    const online = device?.status === 'online';

    // 健康度：efficiency utilization.current 真实值优先；无则在线状态确定性兜底
    let health = online ? 85 : 0;
    try {
      const effRes = await efficiencyAPI.deviceEfficiency(id);
      const cur = effRes.data?.data?.utilization?.current;
      if (typeof cur === 'number') health = Math.round(cur);
    } catch { /* 降级为在线派生健康度 */ }

    // 温度/电压/功率：telemetry stats 真实均值；电流后端无 → P=UI 推导
    let temperature = 0, voltage = 0, power = 0, current = 0;
    try {
      const statRes = await telemetryAPI.stats(id);
      const s = statRes.data?.data?.stats || {};
      const tempSrc = s.thermal?.avg_temp ?? s.thermal?.avg_internal_temp ?? s.battery?.avg_temp;
      const voltSrc = s.grid?.avg_voltage_a;
      const powerSrc = s.grid?.avg_power ?? s.battery?.avg_power ?? s.charger?.avg_power ?? s.pv?.avg_power;
      if (typeof tempSrc === 'number') temperature = +tempSrc.toFixed(1);
      if (typeof voltSrc === 'number') voltage = +voltSrc.toFixed(1);
      if (typeof powerSrc === 'number') power = +powerSrc.toFixed(2);
      if (power > 0 && voltage > 0) current = +(power * 1000 / voltage).toFixed(2);
    } catch { /* 降级为 0 */ }

    return {
      deviceId: id,
      deviceName,
      healthScore: health,
      status: online ? 'online' : 'offline',
      metrics: [
        { label: '温度', key: 'temperature', unit: '°C', value: temperature, maxValue: 100, color: '#ee6666' },
        { label: '电压', key: 'voltage', unit: 'V', value: voltage, maxValue: 380, color: '#5470c6' },
        { label: '电流', key: 'current', unit: 'A', value: current, maxValue: 100, color: '#91cc75' },
        { label: '功率', key: 'power', unit: 'kW', value: power, maxValue: 50, color: '#fac858' },
        { label: '健康度', key: 'health', unit: '分', value: health, maxValue: 100, color: '#73c0de' },
      ],
    };
  };

  const runComparison = useCallback(async () => {
    if (selectedDevices.length < 2) {
      message.warning('请选择至少2个设备进行对比');
      return;
    }
    setLoading(true);
    try {
      // 每设备并行取真实 efficiency + stats；/analytics/compare 后端无可用字段，弃用
      const results = await Promise.all(selectedDevices.map(id => loadDeviceCompare(id)));
      setCompareData(results);
    } catch {
      setCompareData(await Promise.all(selectedDevices.map(id => loadDeviceCompare(id))));
    }
    setLoading(false);
  }, [selectedDevices, allDevices]);

  // 雷达图配置
  const getRadarOption = () => {
    if (compareData.length === 0) return {};

    const indicator = defaultMetricDefs.map(m => ({
      name: m.label,
      max: m.maxValue || 100,
    }));

    const series = [{
      type: 'radar' as const,
      data: compareData.map(d => ({
        value: d.metrics.map(m => m.value),
        name: d.deviceName,
        lineStyle: { width: 2 },
        areaStyle: { opacity: 0.1 },
      })),
    }];

    return {
      title: {
        text: '多设备雷达对比',
        left: 'center',
        textStyle: { fontSize: 14, color: '#1890ff' },
      },
      tooltip: {
        trigger: 'item' as const,
        formatter: (params: any) => {
          const device = compareData[params.seriesIndex];
          if (!device) return '';
          return `<strong>${device.deviceName}</strong><br/>` +
            device.metrics.map(m => `${m.label}: ${m.value}${m.unit}`).join('<br/>');
        },
      },
      legend: {
        data: compareData.map(d => d.deviceName),
        top: 30,
        type: 'scroll' as const,
      },
      radar: {
        indicator,
        center: ['50%', '55%'],
        radius: '65%',
        shape: 'polygon' as const,
        splitNumber: 4,
        axisName: {
          color: '#666',
          fontSize: 11,
        },
        splitLine: {
          lineStyle: { color: 'rgba(0,0,0,0.1)' },
        },
        splitArea: {
          areaStyle: { color: ['rgba(24,144,255,0.02)', 'rgba(24,144,255,0.05)'] },
        },
      },
      series,
    };
  };

  // 柱状图配置
  const getBarOption = () => {
    if (compareData.length === 0) return {};

    const metricKeys = defaultMetricDefs.map(m => m.key);
    const metricLabels = defaultMetricDefs.map(m => m.label);

    const series = metricKeys.map((key, idx) => ({
      name: metricLabels[idx],
      type: 'bar' as const,
      data: compareData.map(d => {
        const metric = d.metrics.find(m => m.key === key);
        return metric?.value ?? 0;
      }),
      itemStyle: { color: defaultMetricDefs[idx].color, borderRadius: [4, 4, 0, 0] },
    }));

    return {
      title: {
        text: '多设备指标对比',
        left: 'center',
        textStyle: { fontSize: 14, color: '#1890ff' },
      },
      tooltip: {
        trigger: 'axis' as const,
        axisPointer: { type: 'shadow' as const },
      },
      legend: {
        data: metricLabels,
        top: 30,
        type: 'scroll' as const,
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        top: '22%',
        containLabel: true,
      },
      xAxis: {
        type: 'category' as const,
        data: compareData.map(d => d.deviceName),
        axisLabel: { rotate: 15, fontSize: 10 },
      },
      yAxis: {
        type: 'value' as const,
        axisLine: { show: false },
        splitLine: { lineStyle: { type: 'dashed', color: '#f0f0f0' } },
      },
      series,
    };
  };

  const handleExport = () => {
    const csvHeader = '设备名称,健康度,状态,' + defaultMetricDefs.map(m => `${m.label}(${m.unit})`).join(',');
    const csvRows = compareData.map(d =>
      [d.deviceName, d.healthScore, d.status, ...d.metrics.map(m => m.value)].join(',')
    );
    const csv = '\uFEFF' + [csvHeader, ...csvRows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `device-comparison-${dayjs().format('YYYYMMDD-HHmmss')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    message.success('对比报告导出成功');
  };

  const deviceOptions = allDevices.map(d => ({
    label: d.name,
    value: d.id,
  }));

  return (
    <div>
      <Row gutter={[16, 16]}>
        {/* 控制栏 */}
        <Col span={24}>
          <Card size="small">
            <Space wrap>
              <Select
                mode="multiple"
                style={{ minWidth: 300, maxWidth: 500 }}
                placeholder="选择要对比的设备 (至少2个)"
                value={selectedDevices}
                onChange={setSelectedDevices}
                options={deviceOptions}
                maxTagCount={5}
              />
              <Button type="primary" icon={<SwapOutlined />} onClick={runComparison} loading={loading}>
                开始对比
              </Button>
              <Button
                icon={chartMode === 'radar' ? <BarChartOutlined /> : <RadarChartOutlined />}
                onClick={() => setChartMode(chartMode === 'radar' ? 'bar' : 'radar')}
              >
                {chartMode === 'radar' ? '柱状图' : '雷达图'}
              </Button>
              {compareData.length > 0 && (
                <Button icon={<DownloadOutlined />} onClick={handleExport}>
                  导出CSV
                </Button>
              )}
            </Space>
          </Card>
        </Col>

        {/* 对比图表 */}
        {compareData.length > 0 && (
          <>
            <Col span={16}>
              <Card loading={loading}>
                <ReactEChartsCore
                  echarts={echarts}
                  option={chartMode === 'radar' ? getRadarOption() : getBarOption()}
                  style={{ width: '100%', height: 420 }}
                  opts={{ renderer: 'svg' }}
                  notMerge={true}
                />
              </Card>
            </Col>

            {/* 健康度概览 */}
            <Col span={8}>
              <Card title="设备健康度概览" loading={loading}>
                <Space direction="vertical" style={{ width: '100%' }}>
                  {compareData.map(d => (
                    <Card key={d.deviceId} size="small" hoverable style={{ width: '100%' }}>
                      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                        <Text strong>{d.deviceName}</Text>
                        <Tag color={d.status === 'online' ? 'green' : 'red'}>
                          {d.status === 'online' ? '在线' : '离线'}
                        </Tag>
                      </Space>
                      <div style={{ marginTop: 8 }}>
                        <Statistic
                          title="健康度评分"
                          value={d.healthScore}
                          suffix="分"
                          valueStyle={{
                            color: d.healthScore >= 90 ? '#52c41a' : d.healthScore >= 70 ? '#faad14' : '#ff4d4f',
                          }}
                        />
                      </div>
                    </Card>
                  ))}
                </Space>
              </Card>
            </Col>

            {/* 对比数据表格 */}
            <Col span={24}>
              <Card title="详细对比数据" size="small">
                <Table
                  dataSource={compareData}
                  rowKey="deviceId"
                  size="small"
                  pagination={false}
                  scroll={{ x: 600 }}
                  columns={[
                    { title: '设备名称', dataIndex: 'deviceName', key: 'deviceName', fixed: 'left', width: 160 },
                    {
                      title: '状态',
                      dataIndex: 'status',
                      key: 'status',
                      width: 80,
                      render: (s: string) => <Tag color={s === 'online' ? 'green' : 'red'}>{s === 'online' ? '在线' : '离线'}</Tag>,
                    },
                    {
                      title: '健康度',
                      dataIndex: 'healthScore',
                      key: 'healthScore',
                      width: 100,
                      sorter: (a: any, b: any) => a.healthScore - b.healthScore,
                      render: (v: number) => (
                        <Tag color={v >= 90 ? 'green' : v >= 70 ? 'orange' : 'red'}>{v}分</Tag>
                      ),
                    },
                    ...defaultMetricDefs.map(m => ({
                      title: `${m.label}(${m.unit})`,
                      key: m.key,
                      width: 120,
                      render: (_: any, record: DeviceCompareData) => {
                        const metric = record.metrics.find(mm => mm.key === m.key);
                        return metric?.value?.toFixed?.(1) ?? '-';
                      },
                    })),
                  ]}
                />
              </Card>
            </Col>
          </>
        )}

        {/* 空状态 */}
        {compareData.length === 0 && !loading && (
          <Col span={24}>
            <Card>
              <Empty description="请选择设备并点击「开始对比」" style={{ padding: 60 }} />
            </Card>
          </Col>
        )}
      </Row>
    </div>
  );
};

export default DeviceComparison;