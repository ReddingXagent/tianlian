/**
 * 发电效率分析 (子页面)
 * 适配后端 GET /reports/generation 实际返回结构:
 * { code:200, data: { items:[...], total, page, page_size, alerts:{ high_performance:{...}, low_performance:{...} } } }
 * item 字段: device_id, device_name, device_code, device_type, station_name, pv_pr_ratio, rated_power_kw, runtime_hours, actual_generation_kwh, theoretical_generation_kwh, generation_ratio
 */
import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Card, Spin, Table, Tag, Select, Button, Empty, Space, Statistic, message } from 'antd';
import {
  ReloadOutlined, WarningOutlined, ThunderboltOutlined,
  SunOutlined, CloudOutlined,
} from '@ant-design/icons';
import * as echarts from 'echarts/core';
import { BarChart } from 'echarts/charts';
import { TitleComponent, TooltipComponent, GridComponent, MarkLineComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([BarChart, TitleComponent, TooltipComponent, GridComponent, MarkLineComponent, CanvasRenderer]);
import api from '../../api';
import { fetchAllPages } from '../../api/fetchAll';

interface GenerationItem {
  device_id: number;
  device_name: string;
  device_code: string;
  device_type: string;
  station_id: number | null;
  station_name: string;
  pv_pr_ratio: number | null;
  rated_power_kw: number;
  runtime_hours: number;
  actual_generation_kwh: number;
  theoretical_generation_kwh: number | null;
  generation_ratio: number | null;
}

interface GenerationResp {
  items: GenerationItem[];
  total: number;
  page: number;
  page_size: number;
  alerts: {
    high_performance: { count: number; threshold: string; items: GenerationItem[] };
    low_performance: { count: number; threshold: string; items: GenerationItem[] };
  };
}

const GenerationEfficiencyAnalysis: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<GenerationResp | null>(null);
  const [period, setPeriod] = useState('30d');
  const barChartRef = useRef<HTMLDivElement>(null);
  const compareChartRef = useRef<HTMLDivElement>(null);
  const barChartInstance = useRef<echarts.ECharts | null>(null);
  const compareChartInstance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    loadData();
    return () => {
      barChartInstance.current?.dispose();
      compareChartInstance.current?.dispose();
    };
  }, []);

  useEffect(() => {
    if (data) {
      renderCharts(data);
    }
  }, [data]);

  const loadData = async () => {
    setLoading(true);
    try {
      let firstPayload: GenerationResp | null = null;
      const items = await fetchAllPages<GenerationItem>((params: Record<string, unknown>) =>
        api.get('/reports/generation', { params }).then((r) => {
          const payload = r.data?.data ?? r.data;
          if (params.page === 1) firstPayload = payload as GenerationResp | null;
          return { data: payload };
        }));
      if (firstPayload) {
        setData({ ...firstPayload, items, total: items.length });
      } else {
        message.warning('暂无发电效率数据');
      }
    } catch {
      message.error('加载发电效率数据失败');
    } finally {
      setLoading(false);
    }
  };

  const renderCharts = (payload: GenerationResp) => {
    const items = payload.items;

    // PR值排名
    if (barChartRef.current && !barChartInstance.current) {
      barChartInstance.current = echarts.init(barChartRef.current);
    }
    if (barChartInstance.current && items.length > 0) {
      const sorted = [...items].sort((a, b) => (b.pv_pr_ratio ?? 0) - (a.pv_pr_ratio ?? 0));
      barChartInstance.current.setOption({
        title: { text: '光伏设备PR值排名', left: 'center' },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          formatter: (params: any) => {
            const p = Array.isArray(params) ? params[0] : params;
            const item = sorted[p.dataIndex];
            return `${item.device_name}<br/>站点: ${item.station_name || '-'}<br/>PR: ${p.value}%`;
          },
        },
        grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
        xAxis: {
          type: 'category',
          data: sorted.map(d => d.device_name),
          axisLabel: { rotate: 30, fontSize: 10 },
        },
        yAxis: { type: 'value', name: 'PR值(%)', min: 0, max: 100 },
        series: [
          {
            name: 'PR值(%)',
            type: 'bar',
            data: sorted.map(d => {
              const val = d.pv_pr_ratio != null ? Number((d.pv_pr_ratio * 100).toFixed(1)) : 0;
              return {
                value: val,
                itemStyle: {
                  color: val < 65 ? '#ff4d4f' : val < 80 ? '#faad14' : '#52c41a',
                },
              };
            }),
            label: { show: true, position: 'top', fontSize: 10, formatter: '{c}%' },
            markLine: {
              silent: true,
              lineStyle: { type: 'dashed' },
              data: [
                { yAxis: 80, lineStyle: { color: '#52c41a' }, label: { formatter: '良好 80%' } },
                { yAxis: 65, lineStyle: { color: '#ff4d4f' }, label: { formatter: '警戒 65%' } },
              ],
            },
          },
        ],
      });
    }

    // 实际 vs 理论对比
    if (compareChartRef.current && !compareChartInstance.current) {
      compareChartInstance.current = echarts.init(compareChartRef.current);
    }
    if (compareChartInstance.current && items.length > 0) {
      const valid = items.filter(d => d.theoretical_generation_kwh != null && d.theoretical_generation_kwh > 0);
      compareChartInstance.current.setOption({
        title: { text: '实际发电 vs 理论发电', left: 'center' },
        tooltip: { trigger: 'axis' },
        legend: { data: ['实际发电(kWh)', '理论发电(kWh)'], top: 'bottom' },
        grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
        xAxis: {
          type: 'category',
          data: valid.map(d => d.device_name),
          axisLabel: { rotate: 30, fontSize: 10 },
        },
        yAxis: { type: 'value', name: '发电量(kWh)' },
        series: [
          {
            name: '实际发电(kWh)',
            type: 'bar',
            data: valid.map(d => Number(d.actual_generation_kwh.toFixed(1))),
            itemStyle: { color: '#69b1ff' },
            label: { show: true, position: 'top', fontSize: 9 },
          },
          {
            name: '理论发电(kWh)',
            type: 'bar',
            data: valid.map(d => Number((d.theoretical_generation_kwh ?? 0).toFixed(1))),
            itemStyle: { color: '#ffc069', opacity: 0.5 },
            label: { show: true, position: 'top', fontSize: 9 },
          },
        ],
      });
    }
  };

  const itemsWithPR = data ? data.items.filter(d => d.pv_pr_ratio != null) : [];
  const avgPR = itemsWithPR.length > 0
    ? Number((itemsWithPR.reduce((a, b) => a + (b.pv_pr_ratio ?? 0), 0) / itemsWithPR.length * 100).toFixed(1))
    : 0;
  const totalActual = data ? data.items.reduce((a, b) => a + b.actual_generation_kwh, 0) : 0;
  const totalTheoretical = data
    ? data.items.reduce((a, b) => a + (b.theoretical_generation_kwh ?? 0), 0)
    : 0;
  const lowCount = data?.alerts?.low_performance?.count ?? 0;
  const lowItems = data?.alerts?.low_performance?.items ?? [];

  const columns = [
    { title: '设备名称', dataIndex: 'device_name', key: 'device_name', width: 130 },
    { title: '设备编码', dataIndex: 'device_code', key: 'device_code', width: 110 },
    { title: '站点', dataIndex: 'station_name', key: 'station_name', width: 120 },
    {
      title: 'PR值',
      dataIndex: 'pv_pr_ratio',
      key: 'pv_pr_ratio',
      width: 90,
      sorter: (a: GenerationItem, b: GenerationItem) => (a.pv_pr_ratio ?? 0) - (b.pv_pr_ratio ?? 0),
      render: (v: number | null) => {
        if (v == null) return <Tag>-</Tag>;
        const pct = Number((v * 100).toFixed(1));
        if (pct < 65) return <Tag color="red">{pct}%</Tag>;
        if (pct < 80) return <Tag color="orange">{pct}%</Tag>;
        return <Tag color="green">{pct}%</Tag>;
      },
    },
    {
      title: '实际发电',
      dataIndex: 'actual_generation_kwh',
      key: 'actual_generation_kwh',
      width: 120,
      render: (v: number) => `${v.toLocaleString()} kWh`,
    },
    {
      title: '理论发电',
      dataIndex: 'theoretical_generation_kwh',
      key: 'theoretical_generation_kwh',
      width: 120,
      render: (v: number | null) => v != null ? `${v.toLocaleString()} kWh` : '-',
    },
    {
      title: '达成率',
      key: 'generation_ratio',
      width: 90,
      render: (_: unknown, record: GenerationItem) => {
        if (record.generation_ratio != null) {
          const pct = Number((record.generation_ratio * 100).toFixed(1));
          return <Tag color={pct < 80 ? 'orange' : 'green'}>{pct}%</Tag>;
        }
        return <Tag>-</Tag>;
      },
    },
  ];

  return (
    <div style={{ padding: 16 }}>
      <Spin spinning={loading}>
        {!data ? (
          <Empty description="暂无发电效率数据">
            <Button type="primary" icon={<ReloadOutlined />} onClick={loadData}>
              重新加载
            </Button>
          </Empty>
        ) : (
          <Row gutter={[16, 16]}>
            <Col span={24}>
              <Space>
                <Select
                  value={period}
                  onChange={setPeriod}
                  style={{ width: 120 }}
                  options={[
                    { value: '7d', label: '近7天' },
                    { value: '30d', label: '近30天' },
                    { value: '90d', label: '近90天' },
                  ]}
                />
                <Button icon={<ReloadOutlined />} onClick={loadData}>
                  刷新
                </Button>
              </Space>
            </Col>

            {/* 概览指标 */}
            <Col span={6}>
              <Card>
                <Statistic
                  title="平均PR值"
                  value={avgPR}
                  suffix="%"
                  prefix={<SunOutlined />}
                  valueStyle={{ color: avgPR < 80 ? '#faad14' : '#52c41a' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="总实际发电量"
                  value={totalActual.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                  suffix="kWh"
                  prefix={<ThunderboltOutlined />}
                  valueStyle={{ color: '#1890ff' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="总理论发电量"
                  value={totalTheoretical.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                  suffix="kWh"
                  prefix={<CloudOutlined />}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="低效光伏设备"
                  value={lowCount}
                  suffix="台"
                  prefix={<WarningOutlined />}
                  valueStyle={{ color: lowCount > 0 ? '#ff4d4f' : '#52c41a' }}
                />
              </Card>
            </Col>

            {/* PR排名柱状图 */}
            <Col span={24}>
              <Card title="光伏设备PR值排名">
                <div ref={barChartRef} style={{ width: '100%', height: 380 }} />
              </Card>
            </Col>

            {/* 实际vs理论对比 */}
            <Col span={24}>
              <Card title="实际发电 vs 理论发电">
                <div ref={compareChartRef} style={{ width: '100%', height: 380 }} />
              </Card>
            </Col>

            {/* 设备明细 */}
            <Col span={24}>
              <Card title="光伏设备PR值明细">
                <Table
                  dataSource={data.items}
                  columns={columns}
                  rowKey="device_id"
                  pagination={{
                    pageSize: 20,
                    showSizeChanger: true,
                    total: data.total,
                  }}
                  size="small"
                />
              </Card>
            </Col>

            {/* 低效设备 */}
            <Col span={24}>
              <Card title="低效光伏设备预警" extra={<Tag color="red">PR &lt; 65%</Tag>}>
                {lowItems.length === 0 ? (
                  <Empty description="无低效设备" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                  <Table
                    dataSource={lowItems}
                    columns={columns}
                    rowKey="device_id"
                    pagination={false}
                    size="small"
                  />
                )}
              </Card>
            </Col>
          </Row>
        )}
      </Spin>
    </div>
  );
};

export default GenerationEfficiencyAnalysis;
