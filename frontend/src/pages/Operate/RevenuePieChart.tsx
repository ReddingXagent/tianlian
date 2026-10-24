/**
 * 运营管理 - 营收按用户类型拆分 饼图组件
 */
import React, { useEffect, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { Card, Statistic, Row, Col, Spin, Select, Empty } from 'antd';
import { PieChartOutlined, DollarOutlined, ThunderboltOutlined, ShoppingCartOutlined } from '@ant-design/icons';
import api from '../../api';

interface RevenueByType {
  user_type: string;
  user_type_label: string;
  order_count: number;
  charge_kwh: number;
  total_amount: number;
  percentage: number;
}

interface RevenueData {
  period: { start: string; end: string };
  summary: {
    total_orders: number;
    total_kwh: number;
    total_amount: number;
  };
  breakdown: RevenueByType[];
}

const PIE_COLORS: Record<string, string> = {
  app: '#1890ff',
  card: '#52c41a',
  vin: '#722ed1',
  interconnect: '#fa8c16',
  enterprise: '#eb2f96',
};

const RevenuePieChart: React.FC = () => {
  const [data, setData] = useState<RevenueData | null>(null);
  const [loading, setLoading] = useState(false);
  const [period, setPeriod] = useState<'today' | '7d' | '30d'>('30d');

  const fetchData = async () => {
    setLoading(true);
    try {
      let params: any = {};
      if (period === 'today') {
        const today = new Date().toISOString().slice(0, 10);
        params = { start_date: today, end_date: today };
      } else if (period === '7d') {
        const end = new Date().toISOString().slice(0, 10);
        const start = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
        params = { start_date: start, end_date: end };
      }
      const res = await api.get('/revenue/by-user-type', { params });
      setData(res.data as any);
    } catch (e) {
      // 静默 - 无数据时显示空状态
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [period]);

  const getPieOption = () => {
    if (!data?.breakdown?.length) return {};

    const chartData = data.breakdown
      .filter(item => item.total_amount > 0)
      .map(item => ({
        name: item.user_type_label,
        value: item.total_amount,
        itemStyle: { color: PIE_COLORS[item.user_type] || '#8c8c8c' },
      }));

    if (chartData.length === 0) return {};

    return {
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          const item = data.breakdown.find(b => b.user_type_label === params.name);
          if (!item) return `${params.name}: ¥${params.value.toFixed(2)} (${params.percent}%)`;
          return `<strong>${params.name}</strong><br/>
            营收: ¥${item.total_amount.toFixed(2)} (${params.percent}%)<br/>
            订单: ${item.order_count} 笔<br/>
            充电量: ${item.charge_kwh.toFixed(2)} kWh`;
        },
      },
      legend: {
        orient: 'vertical',
        right: 10,
        top: 'center',
        textStyle: { fontSize: 12 },
      },
      series: [{
        name: '营收分布',
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['40%', '50%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 4,
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: {
          show: true,
          formatter: '{b}\n{d}%',
          fontSize: 11,
        },
        emphasis: {
          label: { fontSize: 16, fontWeight: 'bold' },
          scaleSize: 10,
        },
        data: chartData,
      }],
    };
  };

  if (loading) {
    return (
      <Card title={<><PieChartOutlined /> 营收按用户类型拆分</>} style={{ marginTop: 16 }}>
        <div style={{ textAlign: 'center', padding: 60 }}>
          <Spin size="large" />
        </div>
      </Card>
    );
  }

  if (!data || data.breakdown?.every(item => item.total_amount === 0)) {
    return (
      <Card title={<><PieChartOutlined /> 营收按用户类型拆分</>}
        extra={
          <Select value={period} onChange={setPeriod} size="small" style={{ width: 100 }}
            options={[
              { label: '今日', value: 'today' },
              { label: '近7天', value: '7d' },
              { label: '近30天', value: '30d' },
            ]} />
        }
        style={{ marginTop: 16 }}>
        <Empty description="暂无营收数据，请先创建充电订单" />
      </Card>
    );
  }

  return (
    <Card
      title={<><PieChartOutlined /> 营收按用户类型拆分</>}
      extra={
        <Select value={period} onChange={setPeriod} size="small" style={{ width: 100 }}
          options={[
            { label: '今日', value: 'today' },
            { label: '近7天', value: '7d' },
            { label: '近30天', value: '30d' },
          ]} />
      }
      style={{ marginTop: 16 }}
    >
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Statistic title="总订单" value={data.summary.total_orders} prefix={<ShoppingCartOutlined />} />
        </Col>
        <Col span={8}>
          <Statistic title="总充电量" value={data.summary.total_kwh} suffix="kWh" precision={2} prefix={<ThunderboltOutlined />} />
        </Col>
        <Col span={8}>
          <Statistic title="总营收" value={data.summary.total_amount} prefix={<DollarOutlined />} precision={2} suffix="元" />
        </Col>
      </Row>
      <ReactECharts option={getPieOption()} style={{ height: 320 }} />
    </Card>
  );
};

export default RevenuePieChart;