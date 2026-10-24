/**
 * 天链 V3 — 经营驾驶舱 (Owner Cockpit)
 *
 * 面向"充电站拥有者/投资人"的单一聚合视图, 回答四个问题:
 *   1. 我的场站赚多少   → 总收入 / 售电量 / 客单价
 *   2. 利用率多少       → 枪位时间利用率
 *   3. 毛利多少         → 收入 - 购电成本 (贡献毛利)
 *   4. 多久回本         → 累计毛利 / 投资额 (ROI) + 预计回本月数
 *
 * 数据来源: GET /api/v1/owner-cockpit/overview
 * 口径定义见后端 app/api/v1/owner_cockpit.py 模块 docstring (响应 caliber 字段同步返回)。
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Card, Row, Col, Statistic, Select, Spin, Empty, Table, Tag, Tooltip } from 'antd';
import {
  DollarOutlined, ThunderboltOutlined, PercentageOutlined, FundOutlined,
  AimOutlined, LineChartOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import api from '../../api';

type OverviewData = {
  period: { start_date: string; end_date: string };
  caliber: Record<string, string | number>;
  summary: {
    revenue: number; energy_kwh: number; order_count: number; avg_per_order: number;
    purchase_cost: number; gross_margin: number; gross_margin_rate: number;
    utilization_rate: number;
  };
  investment: {
    total_cost: number | null; cumulative_gross_margin: number;
    roi_rate: number | null; payback_months: number | null;
  };
  stations: Array<{
    station_id: number; station_name: string; revenue: number; energy_kwh: number;
    order_count: number; gross_margin: number; gross_margin_rate: number;
    utilization_rate: number; gun_count: number; total_cost: number | null;
    cumulative_gross_margin: number; roi_rate: number | null;
  }>;
  trend: Array<{ date: string; revenue: number; energy_kwh: number; gross_margin: number }>;
};

const RANGE_PRESETS = [
  { label: '近7天', value: 7 },
  { label: '近30天', value: 30 },
  { label: '近90天', value: 90 },
  { label: '近一年', value: 365 },
];

const OwnerCockpit: React.FC = () => {
  const [days, setDays] = useState<number>(30);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<OverviewData | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const end = dayjs().format('YYYY-MM-DD');
      const start = dayjs().subtract(days, 'day').format('YYYY-MM-DD');
      const res = await api.get('/owner-cockpit/overview', {
        params: { start_date: start, end_date: end },
      });
      // 响应拦截器已解包后端统一响应, res.data 即 payload
      setData((res as any).data ?? null);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const summary = data?.summary;
  const investment = data?.investment;

  const getTrendOption = () => {
    const trend = data?.trend || [];
    if (!trend.length) return {};
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['收入(元)', '毛利(元)'] },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: trend.map((t) => t.date) },
      yAxis: { type: 'value', name: '元' },
      series: [
        { name: '收入(元)', type: 'line', smooth: true, areaStyle: { opacity: 0.1 },
          data: trend.map((t) => t.revenue), itemStyle: { color: '#1890ff' } },
        { name: '毛利(元)', type: 'line', smooth: true,
          data: trend.map((t) => t.gross_margin), itemStyle: { color: '#52c41a' } },
      ],
    };
  };

  const columns = [
    { title: '站点', dataIndex: 'station_name', key: 'station_name' },
    { title: '收入(元)', dataIndex: 'revenue', key: 'revenue', align: 'right' as const,
      render: (v: number) => <span style={{ fontWeight: 600 }}>¥{(v || 0).toFixed(2)}</span> },
    { title: '毛利(元)', dataIndex: 'gross_margin', key: 'gross_margin', align: 'right' as const,
      render: (v: number) => `¥${(v || 0).toFixed(2)}` },
    { title: '毛利率', dataIndex: 'gross_margin_rate', key: 'gross_margin_rate', align: 'right' as const,
      render: (v: number) => `${(v || 0).toFixed(1)}%` },
    { title: '利用率', dataIndex: 'utilization_rate', key: 'utilization_rate', align: 'right' as const,
      render: (v: number) => (
        <Tag color={(v || 0) > 30 ? 'green' : (v || 0) > 10 ? 'orange' : 'red'}>
          {(v || 0).toFixed(2)}%
        </Tag>
      ) },
    { title: 'ROI', dataIndex: 'roi_rate', key: 'roi_rate', align: 'right' as const,
      render: (v: number | null) => v == null ? <Tag>未设投资额</Tag> : `${v.toFixed(2)}%` },
  ];

  return (
    <Card
      title="经营驾驶舱"
      extra={
        <Select
          value={days}
          onChange={(v) => setDays(v)}
          style={{ width: 110 }}
          options={RANGE_PRESETS}
        />
      }
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
      ) : (
        <>
          {/* 经营 KPI */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} md={6}>
              <Card><Statistic title="总收入" value={summary?.revenue || 0} precision={2} prefix={<DollarOutlined />} valueStyle={{ color: '#1890ff' }} suffix="元" /></Card>
            </Col>
            <Col xs={12} md={6}>
              <Card><Statistic title="毛利" value={summary?.gross_margin || 0} precision={2} prefix={<FundOutlined />} valueStyle={{ color: '#52c41a' }} suffix="元" /></Card>
            </Col>
            <Col xs={12} md={6}>
              <Card><Statistic title="毛利率" value={summary?.gross_margin_rate || 0} precision={1} prefix={<PercentageOutlined />} valueStyle={{ color: '#722ed1' }} suffix="%" /></Card>
            </Col>
            <Col xs={12} md={6}>
              <Card><Statistic title="枪位利用率" value={summary?.utilization_rate || 0} precision={2} prefix={<AimOutlined />} suffix="%" /></Card>
            </Col>
          </Row>

          {/* 辅助指标 + ROI */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} md={6}>
              <Card><Statistic title="售电量" value={summary?.energy_kwh || 0} precision={2} prefix={<ThunderboltOutlined />} valueStyle={{ color: '#13c2c2' }} suffix="kWh" /></Card>
            </Col>
            <Col xs={12} md={6}>
              <Card><Statistic title="客单价" value={summary?.avg_per_order || 0} precision={2} prefix={<DollarOutlined />} suffix="元" /></Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Statistic
                  title={<Tooltip title={data?.caliber?.roi_rate as string || '累计毛利/投资额'}>投资回报 ROI</Tooltip>}
                  value={investment?.roi_rate == null ? '—' : investment.roi_rate}
                  precision={2}
                  prefix={<LineChartOutlined />}
                  valueStyle={{ color: (investment?.roi_rate || 0) >= 0 ? '#52c41a' : '#ff4d4f' }}
                  suffix={investment?.roi_rate == null ? '' : '%'}
                />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card><Statistic title="预计回本" value={investment?.payback_months == null ? '—' : investment.payback_months} precision={1} suffix={investment?.payback_months == null ? '' : '个月'} /></Card>
            </Col>
          </Row>

          {/* 投资明细行 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} md={8}>
              <Card size="small"><Statistic title="投资总额 (Σ 站点成本)" value={investment?.total_cost == null ? '—' : investment.total_cost} precision={2} prefix="¥" /></Card>
            </Col>
            <Col xs={24} md={8}>
              <Card size="small"><Statistic title="累计毛利 (全时段)" value={investment?.cumulative_gross_margin || 0} precision={2} prefix="¥" valueStyle={{ color: '#52c41a' }} /></Card>
            </Col>
            <Col xs={24} md={8}>
              <Card size="small"><Statistic title="购电成本" value={summary?.purchase_cost || 0} precision={2} prefix="¥" valueStyle={{ color: '#fa541c' }} /></Card>
            </Col>
          </Row>

          {/* 趋势图 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col span={24}>
              <Card title="收入 · 毛利趋势" size="small">
                {data?.trend?.length ? (
                  <ReactECharts option={getTrendOption()} style={{ height: 300 }} />
                ) : (
                  <Empty description="暂无趋势数据" style={{ padding: 40 }} />
                )}
              </Card>
            </Col>
          </Row>

          {/* 站点明细 */}
          <Card title="站点经营明细" size="small">
            {data?.stations?.length ? (
              <Table
                columns={columns}
                dataSource={data.stations}
                rowKey="station_id"
                pagination={false}
                size="small"
              />
            ) : (
              <Empty description="暂无站点数据" style={{ padding: 40 }} />
            )}
          </Card>
        </>
      )}
    </Card>
  );
};

export default OwnerCockpit;
