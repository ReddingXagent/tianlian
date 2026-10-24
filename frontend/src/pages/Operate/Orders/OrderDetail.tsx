/**
 * 订单详情 Drawer — 展示5项费用拆解 + 基本信息
 */
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Drawer, Descriptions, Tag, Table, Statistic, Row, Col, Spin, Empty, Button, Space, message,
} from 'antd';
import ReactECharts from 'echarts-for-react';
import { operateOrderAPI } from '../../../api/operate';

interface FeeItem {
  id: number;
  order_id: number;
  fee_type: string | null;
  fee_name: string;
  quantity: number;
  unit_price: number;
  amount: number;
  unit: string | null;
  remark: string | null;
  created_at: string | null;
}

interface OrderInfo {
  id: number;
  order_no: string;
  station_name: string;
  plate_number: string;
  user_type: string | null;
  charged_kwh: number;
  total_amount: number;
  paid_amount: number;
  discount_amount: number;
  order_status: string | null;
  payment_status: string | null;
  payment_method: string | null;
  duration_minutes: number;
  created_at: string | null;
}

interface Props {
  open: boolean;
  order: OrderInfo | null;
  onClose: () => void;
}

interface CurvePoint {
  record_time: string | null;
  current_power: number | null;
  energy_this_minute: number | null;
  voltage: number | null;
  current: number | null;
  soc: number | null;
}

const FEE_TYPE_LABELS: Record<string, string> = {
  electricity: '电费',
  service: '服务费',
  parking: '停车费',
  occupancy: '占桩费',
  reservation: '预约费',
  discount: '折扣',
  coupon: '优惠券',
  points: '积分',
};

const FEE_TYPE_COLORS: Record<string, string> = {
  electricity: '#1890ff',
  service: '#52c41a',
  parking: '#fa8c16',
  occupancy: '#eb2f96',
  reservation: '#722ed1',
  discount: '#f5222d',
  coupon: '#13c2c2',
  points: '#faad14',
};

const OrderDetailDrawer: React.FC<Props> = ({ open, order, onClose }) => {
  const [feeItems, setFeeItems] = useState<FeeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [chargeCurve, setChargeCurve] = useState<CurvePoint[]>([]);
  const [curveLoading, setCurveLoading] = useState(false);

  const loadFeeItems = useCallback(async () => {
    if (!order?.id) return;
    setLoading(true);
    try {
      const { data } = await operateOrderAPI.getFeeItems(order.id);
      setFeeItems(Array.isArray(data) ? data : []);
    } catch {
      setFeeItems([]);
    } finally {
      setLoading(false);
    }
  }, [order?.id]);

  const loadChargeCurve = useCallback(async () => {
    if (!order?.id) return;
    setCurveLoading(true);
    try {
      const { data } = await operateOrderAPI.getChargeCurve(order.id);
      // 兼容后端 { items } 结构与兜底空数组
      setChargeCurve(Array.isArray(data) ? [] : (data?.items ?? []));
    } catch {
      setChargeCurve([]);
    } finally {
      setCurveLoading(false);
    }
  }, [order?.id]);

  useEffect(() => {
    if (open && order?.id) {
      loadFeeItems();
      loadChargeCurve();
    }
  }, [open, order?.id, loadFeeItems, loadChargeCurve]);

  // 充电曲线 echarts 配置 — 双 Y 轴: 左轴功率/电量, 右轴 SOC
  const curveOption = useMemo(() => {
    const times = chargeCurve.map(p =>
      p.record_time ? new Date(p.record_time).toLocaleTimeString('zh-CN', { hour12: false }) : '-'
    );
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['功率(kW)', '电量(kWh)', 'SOC(%)'], top: 0 },
      grid: { left: 56, right: 56, top: 36, bottom: 24 },
      xAxis: { type: 'category', data: times, boundaryGap: false },
      yAxis: [
        { type: 'value', name: 'kW/kWh', position: 'left' },
        { type: 'value', name: 'SOC%', position: 'right', min: 0, max: 100 },
      ],
      series: [
        { name: '功率(kW)', type: 'line', smooth: true, symbol: 'none', itemStyle: { color: '#1890ff' }, data: chargeCurve.map(p => p.current_power) },
        { name: '电量(kWh)', type: 'line', smooth: true, symbol: 'none', itemStyle: { color: '#52c41a' }, data: chargeCurve.map(p => p.energy_this_minute) },
        { name: 'SOC(%)', type: 'line', smooth: true, symbol: 'none', yAxisIndex: 1, itemStyle: { color: '#fa8c16' }, data: chargeCurve.map(p => p.soc) },
      ],
    };
  }, [chargeCurve]);

  // 计算5项费用汇总
  const feeSummary = {
    electricity: feeItems.filter(f => f.fee_type === 'electricity').reduce((s, f) => s + f.amount, 0),
    service: feeItems.filter(f => f.fee_type === 'service').reduce((s, f) => s + f.amount, 0),
    parking: feeItems.filter(f => f.fee_type === 'parking').reduce((s, f) => s + f.amount, 0),
    occupancy: feeItems.filter(f => f.fee_type === 'occupancy').reduce((s, f) => s + f.amount, 0),
    reservation: feeItems.filter(f => f.fee_type === 'reservation').reduce((s, f) => s + f.amount, 0),
  };

  const feeColumns = [
    {
      title: '费用类型', dataIndex: 'fee_type', key: 'fee_type', width: 100,
      render: (v: string | null) => v ? <Tag color={FEE_TYPE_COLORS[v] || 'default'}>{FEE_TYPE_LABELS[v] || v}</Tag> : '-',
    },
    { title: '名称', dataIndex: 'fee_name', key: 'fee_name', width: 120 },
    { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 90, align: 'right' as const, render: (v: number) => v?.toFixed(2) },
    { title: '单价', dataIndex: 'unit_price', key: 'unit_price', width: 90, align: 'right' as const, render: (v: number) => `¥${v?.toFixed(4)}` },
    { title: '单位', dataIndex: 'unit', key: 'unit', width: 70 },
    {
      title: '金额', dataIndex: 'amount', key: 'amount', width: 110, align: 'right' as const,
      render: (v: number) => (
        <span style={{ fontWeight: 600, color: v >= 0 ? '#34a853' : '#ea4335' }}>
          ¥{Math.abs(v).toFixed(2)}
        </span>
      ),
    },
  ];

  return (
    <Drawer
      title={order ? `订单详情 - ${order.order_no}` : '订单详情'}
      open={open}
      onClose={onClose}
      width={720}
      destroyOnHidden
    >
      {order && (
        <>
          <Descriptions title="基本信息" bordered column={2} size="small" style={{ marginBottom: 24 }}>
            <Descriptions.Item label="订单号">{order.order_no}</Descriptions.Item>
            <Descriptions.Item label="站点">{order.station_name}</Descriptions.Item>
            <Descriptions.Item label="车牌号">{order.plate_number || '-'}</Descriptions.Item>
            <Descriptions.Item label="用户类型">{order.user_type || '-'}</Descriptions.Item>
            <Descriptions.Item label="充电量">{order.charged_kwh?.toFixed(2)} kWh</Descriptions.Item>
            <Descriptions.Item label="充电时长">{order.duration_minutes} 分钟</Descriptions.Item>
            <Descriptions.Item label="订单状态">
              <Tag color={order.order_status === 'completed' ? 'green' : 'orange'}>
                {order.order_status || '-'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="支付状态">
              <Tag color={order.payment_status === 'paid' ? 'green' : 'blue'}>
                {order.payment_status || '-'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="支付方式">{order.payment_method || '-'}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{order.created_at ? new Date(order.created_at).toLocaleString('zh-CN') : '-'}</Descriptions.Item>
          </Descriptions>

          {/* 5项费用汇总 */}
          <Row gutter={[12, 12]} style={{ marginBottom: 24 }}>
            <Col span={4}>
              <Statistic title="电费" value={feeSummary.electricity} precision={2} prefix="¥" valueStyle={{ fontSize: 14 }} />
            </Col>
            <Col span={5}>
              <Statistic title="服务费" value={feeSummary.service} precision={2} prefix="¥" valueStyle={{ fontSize: 14 }} />
            </Col>
            <Col span={4}>
              <Statistic title="停车费" value={feeSummary.parking} precision={2} prefix="¥" valueStyle={{ fontSize: 14 }} />
            </Col>
            <Col span={5}>
              <Statistic title="占桩费" value={feeSummary.occupancy} precision={2} prefix="¥" valueStyle={{ fontSize: 14 }} />
            </Col>
            <Col span={6}>
              <Statistic title="预约费" value={feeSummary.reservation} precision={2} prefix="¥" valueStyle={{ fontSize: 14 }} />
            </Col>
          </Row>

          {/* 金额汇总 */}
          <Row gutter={[12, 12]} style={{ marginBottom: 24 }}>
            <Col span={8}>
              <Statistic title="订单总额" value={order.total_amount} precision={2} prefix="¥" />
            </Col>
            <Col span={8}>
              <Statistic title="优惠金额" value={order.discount_amount} precision={2} prefix="¥" valueStyle={{ color: '#ea4335' }} />
            </Col>
            <Col span={8}>
              <Statistic title="实付金额" value={order.paid_amount} precision={2} prefix="¥" valueStyle={{ color: '#34a853' }} />
            </Col>
          </Row>

          {/* 费用明细表 */}
          <Space style={{ marginBottom: 12 }}>
            <h3>费用明细</h3>
            <Button size="small" onClick={loadFeeItems} loading={loading}>刷新</Button>
          </Space>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
          ) : feeItems.length > 0 ? (
            <Table
              columns={feeColumns}
              dataSource={feeItems}
              rowKey="id"
              pagination={false}
              size="small"
            />
          ) : (
            <Empty description="暂无费用明细，请先结算订单" />
          )}

          {/* 充电曲线 — 功率/电量/SOC 时间序列 */}
          <h3 style={{ marginTop: 24 }}>充电曲线</h3>
          {curveLoading ? (
            <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
          ) : chargeCurve.length > 0 ? (
            <ReactECharts option={curveOption} style={{ height: 280 }} />
          ) : (
            <Empty description="暂无充电曲线数据" />
          )}
        </>
      )}
    </Drawer>
  );
};

export default OrderDetailDrawer;
