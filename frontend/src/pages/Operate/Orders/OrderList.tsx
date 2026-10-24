/**
 * 订单列表 — 多维度筛选(用户类型/站点/时间/金额/状态) + 详情 Drawer
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table, Tag, Button, Space, Input, Select, DatePicker, Card, Row, Col, Statistic, message,
} from 'antd';
import {
  ReloadOutlined, SearchOutlined, EyeOutlined, ShoppingCartOutlined,
  DollarOutlined, CheckCircleOutlined, ClockCircleOutlined, DownloadOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { operateOrderAPI } from '../../../api/operate';
import { exportObjectsCSV } from '../../../utils/csvExport';
import OrderDetailDrawer from './OrderDetail';

const { RangePicker } = DatePicker;

/* ── 状态映射 ── */
const ORDER_STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待处理' },
  charging: { color: 'blue', text: '充电中' },
  completed: { color: 'green', text: '已完成' },
  cancelled: { color: 'red', text: '已取消' },
  failed: { color: 'red', text: '失败' },
};

const PAYMENT_STATUS_MAP: Record<string, { color: string; text: string }> = {
  unpaid: { color: 'default', text: '未支付' },
  paid: { color: 'green', text: '已支付' },
  partial: { color: 'orange', text: '部分支付' },
  refunding: { color: 'blue', text: '退款中' },
  refunded: { color: 'purple', text: '已退款' },
};

const USER_TYPE_MAP: Record<string, string> = {
  app: 'APP用户',
  card: '刷卡用户',
  vin: 'VIN码用户',
  interconnect: '互联互通',
  enterprise: '企业用户',
};

interface OrderRow {
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
  onRefundsChange?: () => void;
}

const OrderListPage: React.FC<Props> = () => {
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // 筛选
  const [keyword, setKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [paymentFilter, setPaymentFilter] = useState<string | undefined>(undefined);
  const [userTypeFilter, setUserTypeFilter] = useState<string | undefined>(undefined);
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null);

  // 详情 Drawer
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState<OrderRow | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (keyword) params.keyword = keyword;
      if (statusFilter) params.status = statusFilter;
      if (paymentFilter) params.payment_status = paymentFilter;
      if (dateRange && dateRange[0]) params.start_date = dateRange[0].format('YYYY-MM-DD');
      if (dateRange && dateRange[1]) params.end_date = dateRange[1].format('YYYY-MM-DD');
      const { data } = await operateOrderAPI.list(params as any);
      setOrders((data as any)?.items || []);
      setTotal((data as any)?.total || 0);
    } catch {
      setOrders([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, keyword, statusFilter, paymentFilter, dateRange]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSearch = () => { setPage(1); loadData(); };
  const handleReset = () => {
    setKeyword(''); setStatusFilter(undefined); setPaymentFilter(undefined);
    setUserTypeFilter(undefined); setDateRange(null); setPage(1);
  };

  const openDetail = (record: OrderRow) => {
    setSelectedOrder(record);
    setDetailOpen(true);
  };

  // 统计
  const stats = {
    total: total,
    totalAmount: orders.reduce((s, o) => s + (o.total_amount || 0), 0),
    paid: orders.filter(o => o.payment_status === 'paid').length,
    pending: orders.filter(o => o.payment_status === 'unpaid' || o.payment_status === 'partial').length,
  };

  const columns = [
    {
      title: '订单号', dataIndex: 'order_no', key: 'order_no', width: 170,
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    { title: '站点', dataIndex: 'station_name', key: 'station_name', width: 130, ellipsis: true },
    { title: '车牌号', dataIndex: 'plate_number', key: 'plate_number', width: 100 },
    {
      title: '用户类型', dataIndex: 'user_type', key: 'user_type', width: 100,
      render: (v: string | null) => v ? <Tag>{USER_TYPE_MAP[v] || v}</Tag> : '-',
    },
    {
      title: '充电量', dataIndex: 'charged_kwh', key: 'charged_kwh', width: 90, align: 'right' as const,
      render: (v: number) => v ? `${v.toFixed(2)} kWh` : '-',
    },
    {
      title: '总金额', dataIndex: 'total_amount', key: 'total_amount', width: 110, align: 'right' as const,
      render: (v: number) => <span style={{ fontWeight: 600 }}>¥{(v || 0).toFixed(2)}</span>,
    },
    {
      title: '实付', dataIndex: 'paid_amount', key: 'paid_amount', width: 110, align: 'right' as const,
      render: (v: number) => <span style={{ color: '#34a853', fontWeight: 600 }}>¥{(v || 0).toFixed(2)}</span>,
    },
    {
      title: '订单状态', dataIndex: 'order_status', key: 'order_status', width: 90,
      render: (v: string | null) => v ? <Tag color={ORDER_STATUS_MAP[v]?.color || 'default'}>{ORDER_STATUS_MAP[v]?.text || v}</Tag> : '-',
    },
    {
      title: '支付状态', dataIndex: 'payment_status', key: 'payment_status', width: 90,
      render: (v: string | null) => v ? <Tag color={PAYMENT_STATUS_MAP[v]?.color || 'default'}>{PAYMENT_STATUS_MAP[v]?.text || v}</Tag> : '-',
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 150,
      render: (v: string | null) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作', key: 'action', width: 80,
      render: (_: unknown, record: OrderRow) => (
        <Button size="small" icon={<EyeOutlined />} onClick={() => openDetail(record)}>详情</Button>
      ),
    },
  ];

  // 客户端按 user_type 过滤 (后端未提供此筛选)
  const displayOrders = userTypeFilter
    ? orders.filter(o => o.user_type === userTypeFilter)
    : orders;

  // 导出当前列表为 CSV
  const handleExportCSV = () => {
    if (displayOrders.length === 0) {
      message.warning('没有数据可导出');
      return;
    }
    exportObjectsCSV('充电订单列表', displayOrders, [
      { key: 'order_no', label: '订单号' },
      { key: 'station_name', label: '站点' },
      { key: 'plate_number', label: '车牌号' },
      { key: 'user_type', label: '用户类型', format: (r) => (r.user_type && USER_TYPE_MAP[r.user_type]) || r.user_type || '' },
      { key: 'charged_kwh', label: '充电量(kWh)' },
      { key: 'duration_minutes', label: '时长(分钟)' },
      { key: 'total_amount', label: '总金额' },
      { key: 'paid_amount', label: '已支付' },
      { key: 'discount_amount', label: '优惠金额' },
      { key: 'order_status', label: '订单状态', format: (r) => (r.order_status && ORDER_STATUS_MAP[r.order_status]?.text) || r.order_status || '' },
      { key: 'payment_status', label: '支付状态', format: (r) => (r.payment_status && PAYMENT_STATUS_MAP[r.payment_status]?.text) || r.payment_status || '' },
      { key: 'payment_method', label: '支付方式' },
      { key: 'created_at', label: '创建时间' },
    ]);
  };

  return (
    <>
      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card><Statistic title="订单总数" value={stats.total} prefix={<ShoppingCartOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="总金额" value={stats.totalAmount} precision={2} prefix={<><DollarOutlined /> ¥</>} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="已支付" value={stats.paid} valueStyle={{ color: '#34a853' }} prefix={<CheckCircleOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="待支付" value={stats.pending} valueStyle={{ color: '#faad14' }} prefix={<ClockCircleOutlined />} /></Card>
        </Col>
      </Row>

      {/* 筛选区 */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap size="middle">
          <Input
            placeholder="搜索订单号/车牌号"
            prefix={<SearchOutlined />}
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            onPressEnter={handleSearch}
            style={{ width: 200 }}
            allowClear
          />
          <Select
            placeholder="订单状态"
            value={statusFilter}
            onChange={setStatusFilter}
            allowClear
            style={{ width: 120 }}
            options={Object.entries(ORDER_STATUS_MAP).map(([k, v]) => ({ label: v.text, value: k }))}
          />
          <Select
            placeholder="支付状态"
            value={paymentFilter}
            onChange={setPaymentFilter}
            allowClear
            style={{ width: 120 }}
            options={Object.entries(PAYMENT_STATUS_MAP).map(([k, v]) => ({ label: v.text, value: k }))}
          />
          <Select
            placeholder="用户类型"
            value={userTypeFilter}
            onChange={setUserTypeFilter}
            allowClear
            style={{ width: 130 }}
            options={Object.entries(USER_TYPE_MAP).map(([k, v]) => ({ label: v, value: k }))}
          />
          <RangePicker
            value={dateRange as any}
            onChange={(dates) => setDateRange(dates as [dayjs.Dayjs | null, dayjs.Dayjs | null] | null)}
            placeholder={['开始日期', '结束日期']}
          />
          <Button icon={<ReloadOutlined />} onClick={handleReset}>重置</Button>
          <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>查询</Button>
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
          <Button icon={<DownloadOutlined />} onClick={handleExportCSV} disabled={displayOrders.length === 0}>导出CSV</Button>
        </Space>
      </Card>

      {/* 订单表格 */}
      <Table
        columns={columns}
        dataSource={displayOrders}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t: number) => `共 ${t} 条`,
          onChange: (p: number, ps: number) => { setPage(p); setPageSize(ps); },
        }}
        scroll={{ x: 1200 }}
      />

      {/* 详情 Drawer */}
      <OrderDetailDrawer
        open={detailOpen}
        order={selectedOrder}
        onClose={() => setDetailOpen(false)}
      />
    </>
  );
};

export default OrderListPage;
