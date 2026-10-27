/**
 * Dashboard 运行效率概览卡片 (Phase48)
 *
 * 三个核心指标:
 *   - 设备利用率 (%)
 *   - 充电效率 (%)
 *   - 发电效率 (%)
 *
 * 每个指标通过进度环/仪表盘展示当前值和平均值
 * 数据源: /reports/utilization, /reports/efficiency, /reports/generation
 * 支持按站点/设备类型切换统计范围
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Card, Row, Col, Select, Space, Spin, Typography, Statistic, Tooltip } from 'antd';
import {
  ThunderboltOutlined,
  DashboardOutlined,
  BulbOutlined,
  FilterOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { GaugeChart, BarChart } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, LegendComponent, TitleComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([GaugeChart, BarChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer]);

import { efficiencyAPI } from '../../api';
import type { UtilizationReport, EfficiencyReport, GenerationReport } from '../../types';

const { Text } = Typography;

interface EfficiencyOverviewCardProps {
  /** 刷新间隔 ms（0 或负数表示不自动刷新） */
  refreshInterval?: number;
}

// ==================== 效率指标常量 ====================
const METRIC_CONFIG = {
  utilization: {
    title: '设备利用率',
    icon: <DashboardOutlined />,
    color: '#1890ff',
    description: '所有设备的平均运行时占比',
  },
  charge_efficiency: {
    title: '充电效率',
    icon: <ThunderboltOutlined />,
    color: '#52c41a',
    description: '充电桩充放电能量转换效率',
  },
  generation_efficiency: {
    title: '发电效率',
    icon: <BulbOutlined />,
    color: '#fa8c16',
    description: '光伏逆变器PR性能比',
  },
};

// ==================== 辅助函数 ====================
function makeGaugeOption(
  value: number,
  avg: number,
  label: string,
  color: string,
) {
  const pct = Math.min(Math.max(value, 0), 100);
  return {
    series: [
      {
        type: 'gauge',
        startAngle: 210,
        endAngle: -30,
        min: 0,
        max: 100,
        center: ['50%', '55%'],
        radius: '78%',
        progress: {
          show: true,
          width: 10,
          roundCap: true,
          itemStyle: { color },
        },
        axisLine: {
          lineStyle: {
            width: 10,
            color: [
              [0.3, '#ff4d4f'],
              [0.6, '#faad14'],
              [0.8, '#52c41a'],
              [1, '#1890ff'],
            ],
          },
        },
        axisTick: { show: false },
        splitLine: { show: false, length: 6 },
        axisLabel: { show: false },
        pointer: { show: true, length: '60%', width: 5 },
        detail: {
          valueAnimation: true,
          formatter: `{value}%`,
          fontSize: 16,
          fontWeight: 'bold',
          color,
          offsetCenter: [0, '38%'],
        },
        title: {
          offsetCenter: [0, '72%'],
          fontSize: 11,
          color: '#999',
        },
        data: [{ value: pct, name: label }],
      },
    ],
  };
}

function makeTrendBarOption(
  data: Array<{ name: string; value: number }>,
  label: string,
  color: string,
) {
  return {
    tooltip: { trigger: 'axis', formatter: '{b}: {c}%' },
    grid: { left: 50, right: 10, top: 10, bottom: 30 },
    xAxis: {
      type: 'category',
      data: data.map((d) => d.name),
      axisLabel: { fontSize: 10, rotate: data.length > 8 ? 45 : 0 },
    },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { fontSize: 10, formatter: '{value}%' } },
    series: [
      {
        type: 'bar',
        data: data.map((d) => ({ value: d.value, itemStyle: { color } })),
        barWidth: data.length > 8 ? '60%' : '50%',
        label: { show: true, position: 'top', fontSize: 10, formatter: '{c}%' },
      },
    ],
  };
}

// ==================== 组件 ====================
const EfficiencyOverviewCard: React.FC<EfficiencyOverviewCardProps> = ({
  refreshInterval = 60000,
}) => {
  const [loading, setLoading] = useState(false);
  const [utilization, setUtilization] = useState<UtilizationReport | null>(null);
  const [efficiency, setEfficiency] = useState<EfficiencyReport | null>(null);
  const [generation, setGeneration] = useState<GenerationReport | null>(null);
  const [filterType, setFilterType] = useState<string>('all');
  const [error, setError] = useState<string | null>(null);

  // ==================== 数据加载 ====================
  const fetchAll = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    setError(null);

    try {
      const params = filterType && filterType !== 'all'
        ? { device_type: filterType }
        : undefined;

      const results = await Promise.allSettled([
        efficiencyAPI.utilization(params),
        efficiencyAPI.efficiency(params),
        efficiencyAPI.generation(params),
      ]);

      if (results[0].status === 'fulfilled') {
        setUtilization(results[0].value.data);
      } else {
        // 静默处理：该指标请求失败，state 保留上一次值
      }
      if (results[1].status === 'fulfilled') {
        setEfficiency(results[1].value.data);
      } else {
        // 静默处理：该指标请求失败，state 保留上一次值
      }
      if (results[2].status === 'fulfilled') {
        setGeneration(results[2].value.data);
      } else {
        // 静默处理：该指标请求失败，state 保留上一次值
      }

      // If all three failed, show error
      if (
        results[0].status === 'rejected' &&
        results[1].status === 'rejected' &&
        results[2].status === 'rejected'
      ) {
        setError('效率数据加载失败，请稍后重试');
      }
    } catch {
      setError('效率数据加载失败');
    } finally {
      setLoading(false);
    }
  }, [filterType]);

  // 初始加载 & 定时刷新
  useEffect(() => {
    fetchAll(true);

    if (refreshInterval > 0) {
      const timer = setInterval(() => fetchAll(false), refreshInterval);
      return () => clearInterval(timer);
    }
    // 说明：fetchAll 身份随 filterType 变化，本 effect 已覆盖挂载与筛选变更两种触发
  }, [fetchAll, refreshInterval]);

  // ==================== 计算衍生指标 ====================
  const utilRate = utilization?.overall_utilization_rate
    ?? (utilization?.sites?.length
      ? Math.round(utilization.sites.reduce((s, i) => s + i.utilization_rate, 0) / utilization.sites.length)
      : 0);

  const chargeEff = efficiency?.avg_charge_efficiency
    ?? (efficiency?.data?.length
      ? Math.round(efficiency.data.reduce((s, i) => s + i.charge_efficiency, 0) / efficiency.data.length)
      : 0);

  const genEff = generation?.avg_pr_ratio
    ?? (generation?.data?.length
      ? Math.round(generation.data.reduce((s, i) => s + (i.pv_pr_ratio || i.generation_efficiency), 0) / generation.data.length)
      : 0);

  // ==================== 站点趋势数据 ====================
  const siteTrendData = utilization?.sites?.map((s) => ({
    name: s.name?.length > 6 ? `${s.name.slice(0, 6)}...` : (s.name || '—'),
    value: s.utilization_rate,
  })) || [];

  const efficientTrendData = efficiency?.data?.slice(0, 10).map((d) => ({
    name: d.device_name?.length > 6 ? `${d.device_name.slice(0, 6)}...` : (d.device_name || '—'),
    value: d.charge_efficiency,
  })) || [];

  const genTrendData = generation?.data?.slice(0, 10).map((d) => ({
    name: d.device_name?.length > 6 ? `${d.device_name.slice(0, 6)}...` : (d.device_name || '—'),
    value: d.pv_pr_ratio || d.generation_efficiency,
  })) || [];

  // ==================== 渲染 ====================
  const renderGaugeCard = (
    metricKey: keyof typeof METRIC_CONFIG,
    value: number,
    subtitle?: string,
  ) => {
    const config = METRIC_CONFIG[metricKey];
    const option = makeGaugeOption(value, value, config.title, config.color);

    return (
      <Card
        size="small"
        style={{ textAlign: 'center' }}
        bodyStyle={{ padding: '12px 8px' }}
      >
        <Space style={{ marginBottom: 4 }}>
          {config.icon}
          <Text strong style={{ color: config.color }}>
            {config.title}
          </Text>
          <Tooltip title={config.description}>
            <InfoCircleOutlined style={{ color: '#bbb', fontSize: 12 }} />
          </Tooltip>
        </Space>
        <ReactEChartsCore
          echarts={echarts}
          option={option}
          style={{ height: 160, width: '100%' }}
          opts={{ renderer: 'svg' }}
          notMerge
        />
        {subtitle && (
          <Text style={{ fontSize: 11, color: '#888' }}>{subtitle}</Text>
        )}
      </Card>
    );
  };

  const renderTrendCard = (
    title: string,
    data: Array<{ name: string; value: number }>,
    color: string,
    chartHeight = 180,
  ) => {
    if (!data.length) {
      return (
        <Card size="small" title={title} style={{ textAlign: 'center' }}>
          <Text type="secondary">暂无数据</Text>
        </Card>
      );
    }
    const option = makeTrendBarOption(data, title, color);
    return (
      <Card size="small" title={title}>
        <ReactEChartsCore
          echarts={echarts}
          option={option}
          style={{ height: chartHeight, width: '100%' }}
          opts={{ renderer: 'svg' }}
          notMerge
        />
      </Card>
    );
  };

  return (
    <Card
      title={
        <Space>
          <DashboardOutlined style={{ color: '#1890ff', fontSize: 16 }} />
          <Text strong>运行效率概览</Text>
          {loading && <Spin size="small" />}
        </Space>
      }
      extra={
        <Select
          style={{ width: 140 }}
          value={filterType}
          onChange={(v) => setFilterType(v)}
          options={[
            { label: '全部设备', value: 'all' },
            { label: '充电桩', value: 'charger' },
            { label: '光伏逆变器', value: 'pv_inverter' },
            { label: '储能PCS', value: 'pcs' },
            { label: '储电池', value: 'battery' },
          ]}
        />
      }
      className="dash-card"
    >
      {error && (
        <Text type="danger" style={{ display: 'block', textAlign: 'center', marginBottom: 8 }}>
          {error}
        </Text>
      )}

      {/* 三个核心指标仪表盘 */}
      <Row gutter={[12, 12]}>
        <Col xs={24} sm={8}>
          {renderGaugeCard('utilization', utilRate, `平均 ${utilRate}%`)}
        </Col>
        <Col xs={24} sm={8}>
          {renderGaugeCard('charge_efficiency', chargeEff, `平均 ${chargeEff}%`)}
        </Col>
        <Col xs={24} sm={8}>
          {renderGaugeCard('generation_efficiency', genEff, `平均 ${genEff}%`)}
        </Col>
      </Row>

      {/* 预警信息 */}
      {utilization?.warnings && utilization.warnings.length > 0 && (
        <Card
          size="small"
          title={
            <Text style={{ color: '#faad14' }}>
              利用率预警 ({utilization.warnings.length})
            </Text>
          }
          style={{ marginTop: 12 }}
          bodyStyle={{ padding: '8px 12px', maxHeight: 120, overflowY: 'auto' }}
        >
          {utilization.warnings.slice(0, 5).map((w, i) => (
            <div key={i} style={{ fontSize: 12, marginBottom: 4, display: 'flex', justifyContent: 'space-between' }}>
              <span>
                <Text type="secondary">{w.station_name}/{w.device_name}</Text>
                <Text style={{ marginLeft: 8, color: w.status === 'low' ? '#fa8c16' : '#ff4d4f' }}>
                  {w.status === 'low' ? '低利用率' : '过载'} {w.utilization_rate}%
                </Text>
              </span>
              <Text type="secondary" style={{ fontSize: 11 }}>{w.suggestion}</Text>
            </div>
          ))}
        </Card>
      )}

      {/* 站点/设备趋势图 */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} md={8}>
          {renderTrendCard('各站点利用率', siteTrendData, '#1890ff')}
        </Col>
        <Col xs={24} md={8}>
          {renderTrendCard('充电效率 Top10', efficientTrendData, '#52c41a')}
        </Col>
        <Col xs={24} md={8}>
          {renderTrendCard('发电效率 Top10', genTrendData, '#fa8c16')}
        </Col>
      </Row>
    </Card>
  );
};

export default EfficiencyOverviewCard;