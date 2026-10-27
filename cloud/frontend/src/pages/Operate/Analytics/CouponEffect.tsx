/**
 * 优惠效果分析 — 券核销率/增量订单/优惠成本vs营收增长/ROI
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Card, Row, Col, Statistic, Select, Spin, Empty, Table, Tag } from 'antd';
import {
  GiftOutlined, CheckCircleOutlined, PercentageOutlined,
  DollarOutlined, RiseOutlined, ShoppingCartOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import api from '../../../api';

const CouponEffect: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [range, setRange] = useState<'day' | 'week' | 'month' | 'year'>('day');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/analytics/coupon-effect', { params: { range } });
      setData(res.data?.data);
    } catch { setData(null); }
    finally { setLoading(false); }
  }, [range]);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) return <Card><div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div></Card>;

  const summary = data?.summary || {};
  const byType = data?.by_type || [];

  const typeColumns = [
    { title: '券类型', dataIndex: 'type_name', key: 'type_name', render: (v: string) => <Tag color="blue">{v}</Tag> },
    { title: '已使用(张)', dataIndex: 'used_count', key: 'used_count', align: 'right' as const },
    { title: '优惠成本(元)', dataIndex: 'total_cost', key: 'total_cost', align: 'right' as const, render: (v: number) => `¥${v.toFixed(2)}` },
  ];

  return (
    <Card title="优惠效果分析" extra={
      <Select value={range} onChange={(v) => setRange(v)} size="small" style={{ width: 100 }}
        options={[
          { label: '按日', value: 'day' }, { label: '按周', value: 'week' },
          { label: '按月', value: 'month' }, { label: '按年', value: 'year' },
        ]} />
    }>
      {summary.total_coupons_issued > 0 || summary.total_orders > 0 ? (
        <>
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} sm={8}>
              <Card><Statistic title="发券总数" value={summary.total_coupons_issued || 0} prefix={<GiftOutlined />} /></Card>
            </Col>
            <Col xs={12} sm={8}>
              <Card><Statistic title="已核销" value={summary.used_coupons || 0} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} /></Card>
            </Col>
            <Col xs={12} sm={8}>
              <Card><Statistic title="核销率" value={summary.redemption_rate || 0} suffix="%" precision={1} prefix={<PercentageOutlined />} valueStyle={{ color: '#1890ff' }} /></Card>
            </Col>
            <Col xs={12} sm={8}>
              <Card><Statistic title="优惠成本(元)" value={summary.total_discount_cost || 0} precision={2} prefix={<DollarOutlined />} valueStyle={{ color: '#ff4d4f' }} /></Card>
            </Col>
            <Col xs={12} sm={8}>
              <Card><Statistic title="券带动订单" value={summary.coupon_orders || 0} prefix={<ShoppingCartOutlined />} /></Card>
            </Col>
            <Col xs={12} sm={8}>
              <Card>
                <Statistic title="ROI" value={summary.roi || 0} prefix={<RiseOutlined />}
                  valueStyle={{ color: (summary.roi || 0) > 1 ? '#52c41a' : '#faad14' }} suffix="x" />
              </Card>
            </Col>
          </Row>

          {byType.length > 0 && (
            <Card title="按券类型拆分" size="small" style={{ marginTop: 16 }}>
              <Table columns={typeColumns} dataSource={byType} rowKey="coupon_type" pagination={false} size="small" />
            </Card>
          )}

          <Card title="核销漏斗" size="small" style={{ marginTop: 16 }}>
            <ReactECharts option={{
              tooltip: { trigger: 'item', formatter: '{b}: {c}' },
              series: [{
                type: 'funnel',
                data: [
                  { name: '发放总数', value: summary.total_coupons_issued || 0, itemStyle: { color: '#1890ff' } },
                  { name: '已核销', value: summary.used_coupons || 0, itemStyle: { color: '#52c41a' } },
                  { name: '已过期', value: summary.expired_coupons || 0, itemStyle: { color: '#faad14' } },
                ],
                label: { show: true, position: 'inside', formatter: '{b}: {c}' },
              }],
            }} style={{ height: 260 }} />
          </Card>
        </>
      ) : <Empty description="暂无优惠效果数据" />}
    </Card>
  );
};

export default CouponEffect;
