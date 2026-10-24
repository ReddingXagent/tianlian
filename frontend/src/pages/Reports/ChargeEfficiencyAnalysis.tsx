/**
 * 充电效率分析 (子页面)
 * 适配后端 GET /reports/efficiency 实际返回结构:
 * { code:200, data: { items:[...], total, page, page_size, alerts:{ abnormal_low_efficiency:{...} } } }
 * item 字段: device_id, device_name, device_code, device_type, station_name, charge_efficiency
 */
import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Card, Spin, Table, Tag, Select, Button, Empty, Space, Statistic, message } from 'antd';
import {
  ReloadOutlined, WarningOutlined, ThunderboltOutlined, ArrowDownOutlined,
} from '@ant-design/icons';
import * as echarts from 'echarts/core';
import { BarChart } from 'echarts/charts';
import { TitleComponent, TooltipComponent, GridComponent, MarkLineComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([BarChart, TitleComponent, TooltipComponent, GridComponent, MarkLineComponent, CanvasRenderer]);
import api from '../../api';
import { fetchAllPages } from '../../api/fetchAll';

interface EfficiencyItem {
  device_id: number;
  device_name: string;
  device_code: string;
  device_type: string;
  station_id: number | null;
  station_name: string;
  charge_efficiency: number;
}

interface EfficiencyResp {
  items: EfficiencyItem[];
  total: number;
  page: number;
  page_size: number;
  alerts: {
    abnormal_low_efficiency: {
      count: number;
      threshold: string;
      items: EfficiencyItem[];
    };
  };
}

const ChargeEfficiencyAnalysis: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<EfficiencyResp | null>(null);
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
      let firstPayload: EfficiencyResp | null = null;
      const items = await fetchAllPages<EfficiencyItem>((params: Record<string, unknown>) =>
        api.get('/reports/efficiency', { params }).then((r) => {
          const payload = r.data?.data ?? r.data;
          if (params.page === 1) firstPayload = payload as EfficiencyResp | null;
          return { data: payload };
        }));
      if (firstPayload) {
        setData({ ...firstPayload, items, total: items.length });
      } else {
        message.warning('暂无充电效率数据');
      }
    } catch {
      message.error('加载充电效率数据失败');
    } finally {
      setLoading(false);
    }
  };

  const renderChart = (payload: EfficiencyResp) => {
    if (barChartRef.current && !barChartInstance.current) {
      barChartInstance.current = echarts.init(barChartRef.current);
    }
    if (barChartInstance.current && payload.items.length > 0) {
      const sorted = [...payload.items].sort(
        (a, b) => b.charge_efficiency - a.charge_efficiency
      );
      barChartInstance.current.setOption({
        title: { text: '设备充电效率排名', left: 'center' },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          formatter: (params: any) => {
            const p = Array.isArray(params) ? params[0] : params;
            const item = sorted[p.dataIndex];
            return `${item.device_name}<br/>站点: ${item.station_name || '-'}<br/>类型: ${item.device_type}<br/>充电效率: ${p.value}%`;
          },
        },
        grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
        xAxis: {
          type: 'category',
          data: sorted.map(d => d.device_name),
          axisLabel: { rotate: 30, fontSize: 10 },
        },
        yAxis: { type: 'value', name: '充电效率(%)', min: 0, max: 100 },
        series: [
          {
            name: '充电效率(%)',
            type: 'bar',
            data: sorted.map(d => {
              const val = Number(d.charge_efficiency.toFixed(1));
              return {
                value: val,
                itemStyle: {
                  color: val < 70 ? '#ff4d4f' : val < 85 ? '#faad14' : '#52c41a',
                },
              };
            }),
            label: { show: true, position: 'top', fontSize: 10, formatter: '{c}%' },
            markLine: {
              silent: true,
              lineStyle: { type: 'dashed', color: '#faad14' },
              data: [{ yAxis: 70, label: { formatter: '低效阈值 70%' } }],
            },
          },
        ],
      });
    }
  };

  const avgCharge = data && data.items.length > 0
    ? Number(
        (data.items.reduce((a, b) => a + b.charge_efficiency, 0) / data.items.length).toFixed(1)
      )
    : 0;

  const lowCount = data?.alerts?.abnormal_low_efficiency?.count ?? 0;
  const lowItems = data?.alerts?.abnormal_low_efficiency?.items ?? [];

  const columns = [
    { title: '设备名称', dataIndex: 'device_name', key: 'device_name', width: 140 },
    { title: '设备编码', dataIndex: 'device_code', key: 'device_code', width: 120 },
    { title: '类型', dataIndex: 'device_type', key: 'device_type', width: 100 },
    { title: '所属站点', dataIndex: 'station_name', key: 'station_name', width: 130 },
    {
      title: '充电效率',
      dataIndex: 'charge_efficiency',
      key: 'charge_efficiency',
      width: 110,
      render: (v: number) => {
        if (v < 70) return <Tag color="red">{v}%</Tag>;
        if (v < 85) return <Tag color="orange">{v}%</Tag>;
        return <Tag color="green">{v}%</Tag>;
      },
    },
    {
      title: '状态',
      key: 'status',
      width: 100,
      render: (_: unknown, record: EfficiencyItem) => {
        if (record.charge_efficiency < 70) return <Tag color="error">异常低效</Tag>;
        if (record.charge_efficiency < 85) return <Tag color="warning">效率偏低</Tag>;
        return <Tag color="success">正常</Tag>;
      },
    },
  ];

  return (
    <div style={{ padding: 16 }}>
      <Spin spinning={loading}>
        {!data ? (
          <Empty description="暂无充电效率数据">
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
                  title="平均充电效率"
                  value={avgCharge}
                  suffix="%"
                  prefix={<ThunderboltOutlined />}
                  valueStyle={{ color: avgCharge < 85 ? '#faad14' : '#1890ff' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="异常低效设备"
                  value={lowCount}
                  suffix="台"
                  prefix={<WarningOutlined />}
                  valueStyle={{ color: lowCount > 0 ? '#ff4d4f' : '#52c41a' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="效率达标设备"
                  value={(data.total ?? 0) - lowCount}
                  suffix="台"
                  prefix={<ThunderboltOutlined />}
                  valueStyle={{ color: '#52c41a' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="设备总数"
                  value={data.total}
                  suffix="台"
                  prefix={<ArrowDownOutlined />}
                />
              </Card>
            </Col>

            {/* 柱状图 */}
            <Col span={24}>
              <Card title="设备充电效率排名">
                <div ref={barChartRef} style={{ width: '100%', height: 380 }} />
              </Card>
            </Col>

            {/* 设备明细 */}
            <Col span={24}>
              <Card title="设备充电效率明细">
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

            {/* 异常低效设备 */}
            <Col span={24}>
              <Card title="异常低效设备预警" extra={<Tag color="red">{lowCount}台异常</Tag>}>
                {lowItems.length === 0 ? (
                  <Empty description="无异常低效设备" image={Empty.PRESENTED_IMAGE_SIMPLE} />
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

export default ChargeEfficiencyAnalysis;
