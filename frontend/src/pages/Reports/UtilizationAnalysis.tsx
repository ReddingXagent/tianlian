/**
 * 设备利用率分析 (子页面)
 * 适配后端 GET /reports/utilization 实际返回结构:
 * { code:200, data: { items:[...], total, page, page_size, alerts:{ low_utilization:{...}, overload:{...} } } }
 */
import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Card, Spin, Table, Tag, Select, Button, Empty, Space, Statistic, message } from 'antd';
import {
  ReloadOutlined, WarningOutlined, ArrowUpOutlined,
  DashboardOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import * as echarts from 'echarts/core';
import { BarChart } from 'echarts/charts';
import { TitleComponent, TooltipComponent, GridComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([BarChart, TitleComponent, TooltipComponent, GridComponent, CanvasRenderer]);
import api from '../../api';
import { fetchAllPages } from '../../api/fetchAll';

interface DeviceItem {
  device_id: number;
  device_name: string;
  device_code: string;
  device_type: string;
  station_id: number | null;
  station_name: string;
  utilization_rate: number;
}

interface UtilizationResp {
  items: DeviceItem[];
  total: number;
  page: number;
  page_size: number;
  alerts: {
    low_utilization: { count: number; threshold: string; items: DeviceItem[] };
    overload: { count: number; threshold: string; items: DeviceItem[] };
  };
}

const UtilizationAnalysis: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<UtilizationResp | null>(null);
  const [period, setPeriod] = useState('30d');
  const barChartRef = useRef<HTMLDivElement>(null);
  const barChartInstance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    loadData();
    return () => {
      barChartInstance.current?.dispose();
    };
  }, []);

  useEffect(() => {
    if (data) {
      renderChart(data);
    }
  }, [data]);

  const loadData = async () => {
    setLoading(true);
    try {
      let firstPayload: UtilizationResp | null = null;
      const items = await fetchAllPages<DeviceItem>((params: Record<string, unknown>) =>
        api.get('/reports/utilization', { params }).then((r) => {
          // 兼容 {code,data} 包裹与已解包两种响应形状
          const payload = r.data?.data ?? r.data;
          if (params.page === 1) firstPayload = payload as UtilizationResp | null;
          return { data: payload };
        }));
      if (firstPayload) {
        setData({ ...firstPayload, items, total: items.length });
      } else {
        message.warning('暂无利用率数据');
      }
    } catch {
      message.error('加载利用率数据失败');
    } finally {
      setLoading(false);
    }
  };

  const renderChart = (payload: UtilizationResp) => {
    if (barChartRef.current && !barChartInstance.current) {
      barChartInstance.current = echarts.init(barChartRef.current);
    }
    if (barChartInstance.current && payload.items.length > 0) {
      const sorted = [...payload.items].sort(
        (a, b) => b.utilization_rate - a.utilization_rate
      );
      barChartInstance.current.setOption({
        title: { text: '设备利用率排名', left: 'center' },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          formatter: (params: any) => {
            const p = Array.isArray(params) ? params[0] : params;
            const item = sorted[p.dataIndex];
            return `${item.device_name}<br/>站点: ${item.station_name || '-'}<br/>利用率: ${p.value}%`;
          },
        },
        grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
        xAxis: {
          type: 'category',
          data: sorted.map(s => s.device_name),
          axisLabel: { rotate: 30, fontSize: 10 },
        },
        yAxis: { type: 'value', name: '利用率(%)', min: 0, max: 100 },
        series: [
          {
            name: '利用率(%)',
            type: 'bar',
            data: sorted.map(s => {
              const val = Number(s.utilization_rate.toFixed(1));
              return {
                value: val,
                itemStyle: {
                  color: val >= 90 ? '#ff4d4f' : val < 30 ? '#faad14' : '#1890ff',
                },
              };
            }),
            label: { show: true, position: 'top', fontSize: 10, formatter: '{c}%' },
          },
        ],
      });
    }
  };

  const avgUtil = data && data.items.length > 0
    ? Number(
        (data.items.reduce((a, b) => a + b.utilization_rate, 0) / data.items.length).toFixed(1)
      )
    : 0;

  const deviceColumns = [
    { title: '设备名称', dataIndex: 'device_name', key: 'device_name', width: 140 },
    { title: '设备编码', dataIndex: 'device_code', key: 'device_code', width: 120 },
    { title: '类型', dataIndex: 'device_type', key: 'device_type', width: 100 },
    { title: '所属站点', dataIndex: 'station_name', key: 'station_name', width: 130 },
    {
      title: '利用率',
      dataIndex: 'utilization_rate',
      key: 'utilization_rate',
      width: 100,
      render: (v: number) => {
        if (v < 30) return <Tag color="orange">{v}%</Tag>;
        if (v > 90) return <Tag color="red">{v}% <WarningOutlined /></Tag>;
        return <Tag color="blue">{v}%</Tag>;
      },
    },
    {
      title: '状态',
      key: 'status',
      width: 100,
      render: (_: unknown, record: DeviceItem) => {
        if (record.utilization_rate < 30) return <Tag color="warning">低利用率</Tag>;
        if (record.utilization_rate > 90) return <Tag color="error">接近过载</Tag>;
        return <Tag color="success">正常</Tag>;
      },
    },
  ];

  return (
    <div style={{ padding: 16 }}>
      <Spin spinning={loading}>
        {!data ? (
          <Empty description="暂无利用率数据">
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
                  title="平均利用率"
                  value={avgUtil}
                  suffix="%"
                  prefix={<DashboardOutlined />}
                  valueStyle={{ color: avgUtil < 60 ? '#faad14' : '#1890ff' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="低利用率设备"
                  value={data.alerts?.low_utilization?.count ?? 0}
                  suffix="台"
                  prefix={<WarningOutlined />}
                  valueStyle={{
                    color: (data.alerts?.low_utilization?.count ?? 0) > 0 ? '#ff4d4f' : '#52c41a',
                  }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="过载设备"
                  value={data.alerts?.overload?.count ?? 0}
                  suffix="台"
                  prefix={<ArrowUpOutlined />}
                  valueStyle={{ color: '#ff4d4f' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="设备总数"
                  value={data.total}
                  suffix="台"
                  prefix={<ThunderboltOutlined />}
                />
              </Card>
            </Col>

            {/* 柱状图 */}
            <Col span={24}>
              <Card title="设备利用率排名">
                <div ref={barChartRef} style={{ width: '100%', height: 380 }} />
              </Card>
            </Col>

            {/* 设备明细 */}
            <Col span={24}>
              <Card title="设备利用率明细">
                <Table
                  dataSource={data.items}
                  columns={deviceColumns}
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

            {/* 低利用率预警 */}
            <Col span={12}>
              <Card title="低利用率设备预警" extra={<Tag color="orange">利用率 &lt; 30%</Tag>}>
                {(!data.alerts?.low_utilization?.items ||
                  data.alerts.low_utilization.items.length === 0) ? (
                  <Empty description="无低利用率设备" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                  <Table
                    dataSource={data.alerts.low_utilization.items}
                    columns={deviceColumns}
                    rowKey="device_id"
                    pagination={false}
                    size="small"
                  />
                )}
              </Card>
            </Col>

            {/* 过载设备 */}
            <Col span={12}>
              <Card title="过载设备标记" extra={<Tag color="red">利用率 &gt; 90%</Tag>}>
                {(!data.alerts?.overload?.items ||
                  data.alerts.overload.items.length === 0) ? (
                  <Empty description="无过载设备" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                  <Table
                    dataSource={data.alerts.overload.items}
                    columns={deviceColumns}
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

export default UtilizationAnalysis;
