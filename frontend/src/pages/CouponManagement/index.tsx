/**
 * 天链 V3 - 优惠券管理页面
 * P0 运营核心补齐：优惠券创建/发放/核销/统计
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Space, Input, InputNumber, Select, message, Popconfirm,
  Modal, Form, Switch, Row, Col, Statistic, Tabs, DatePicker,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, SearchOutlined,
  DollarOutlined, GiftOutlined, CheckCircleOutlined, FileTextOutlined, BarChartOutlined,
} from '@ant-design/icons';
import api from '../../api';
import { fetchAllPages } from '../../api/fetchAll';
import PageWrapper from '../../components/PageWrapper';

/* ── 类型定义 ── */
interface Coupon {
  id: number;
  name: string;
  coupon_type: 'fixed' | 'percentage' | 'free_charge' | 'service_free';
  face_value: number;
  min_order_amount: number;
  max_discount_amount?: number;
  applicable_user_types?: string;
  applicable_stations?: string;
  total_stock: number;
  remaining_stock: number;
  per_user_limit: number;
  valid_days: number;
  start_time: string;
  end_time: string;
  is_active: boolean;
  description?: string;
  created_at: string;
  updated_at: string;
}

interface CouponBatch {
  id: number;
  coupon_id: number;
  batch_name: string;
  quantity: number;
  user_type?: string;
  user_ids?: string;
  distributed_at: string;
  created_at: string;
}

interface CouponUsage {
  id: number;
  coupon_id: number;
  batch_id?: number;
  user_id: number;
  user_type?: string;
  coupon_code: string;
  order_id?: number;
  status: 'active' | 'used' | 'expired' | 'disabled';
  discount_amount?: number;
  used_at?: string;
  expires_at: string;
  received_at: string;
  created_at: string;
}

const COUPON_TYPE_MAP: Record<string, { color: string; text: string }> = {
  fixed: { color: 'blue', text: '固定金额' },
  percentage: { color: 'purple', text: '百分比折扣' },
  free_charge: { color: 'green', text: '免单券' },
  service_free: { color: 'orange', text: '免服务费' },
};

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  active: { color: 'green', text: '可用' },
  used: { color: 'blue', text: '已使用' },
  expired: { color: 'red', text: '已过期' },
  disabled: { color: 'gray', text: '已停用' },
};

const USER_TYPE_MAP: Record<string, string> = {
  app: 'APP用户',
  card: '卡用户',
  vin: 'VIN用户',
  interconnect: '互联互通用户',
  enterprise: '企业用户',
};

/* ── 组件 ── */
const CouponManagement: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'coupons' | 'batches' | 'usages' | 'stats'>('coupons');
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [batches, setBatches] = useState<CouponBatch[]>([]);
  const [usages, setUsages] = useState<CouponUsage[]>([]);
  const [stats, setStats] = useState<any>({});
  const [couponLoading, setCouponLoading] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const [usageLoading, setUsageLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [couponModalOpen, setCouponModalOpen] = useState(false);
  const [batchModalOpen, setBatchModalOpen] = useState(false);
  const [editingCoupon, setEditingCoupon] = useState<Coupon | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [couponForm] = Form.useForm();
  const [batchForm] = Form.useForm();

  const fetchCoupons = useCallback(async () => {
    setCouponLoading(true);
    try {
      const extra: Record<string, unknown> = {};
      if (searchText) extra.search = searchText;
      const items = await fetchAllPages<Coupon>((params) => api.get('/operate/coupon', { params }), extra);
      setCoupons(items);
    } catch { message.error('加载优惠券失败'); }
    finally { setCouponLoading(false); }
  }, [searchText]);

  const fetchBatches = useCallback(async () => {
    setBatchLoading(true);
    try {
      const items = await fetchAllPages<CouponBatch>((params) => api.get('/operate/coupon/batches', { params }));
      setBatches(items);
    } catch { message.error('加载发放批次失败'); setBatches([]); }
    finally { setBatchLoading(false); }
  }, []);

  const fetchUsages = useCallback(async () => {
    setUsageLoading(true);
    try {
      const items = await fetchAllPages<CouponUsage>((params) => api.get('/operate/coupon/usages', { params }));
      setUsages(items);
    } catch { message.error('加载使用记录失败'); setUsages([]); }
    finally { setUsageLoading(false); }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const res = await api.get('/operate/coupon/stats');
      setStats(res.data || {});
    } catch { }
  }, []);

  useEffect(() => {
    fetchCoupons();
    fetchBatches();
    fetchUsages();
    fetchStats();
  }, [fetchCoupons, fetchBatches, fetchUsages, fetchStats]);

  const openCreateCoupon = () => {
    setEditingCoupon(null);
    couponForm.resetFields();
    couponForm.setFieldsValue({
      coupon_type: 'fixed',
      face_value: 10,
      min_order_amount: 0,
      per_user_limit: 1,
      valid_days: 30,
      total_stock: 100,
      is_active: true,
      start_time: new Date(),
      end_time: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000),
    });
    setCouponModalOpen(true);
  };

  const openEditCoupon = (record: Coupon) => {
    setEditingCoupon(record);
    couponForm.setFieldsValue({
      name: record.name,
      coupon_type: record.coupon_type,
      face_value: record.face_value,
      min_order_amount: record.min_order_amount,
      max_discount_amount: record.max_discount_amount || '',
      applicable_user_types: record.applicable_user_types || '',
      applicable_stations: record.applicable_stations || '',
      total_stock: record.total_stock,
      per_user_limit: record.per_user_limit,
      valid_days: record.valid_days,
      is_active: record.is_active,
      description: record.description || '',
      start_time: new Date(record.start_time),
      end_time: new Date(record.end_time),
    });
    setCouponModalOpen(true);
  };

  const handleCouponSubmit = async (values: any) => {
    setSubmitting(true);
    try {
      const payload = {
        ...values,
        start_time: values.start_time?.toISOString(),
        end_time: values.end_time?.toISOString(),
        applicable_user_types: values.applicable_user_types || undefined,
        applicable_stations: values.applicable_stations || undefined,
        max_discount_amount: values.max_discount_amount || undefined,
        remaining_stock: values.total_stock, // 新建时剩余=总数
      };
      if (editingCoupon) {
        await api.put(`/operate/coupon/${editingCoupon.id}`, payload);
        message.success('更新成功');
      } else {
        await api.post('/operate/coupon', payload);
        message.success('创建成功');
      }
      setCouponModalOpen(false);
      fetchCoupons();
    } catch (e) {
      message.error(editingCoupon ? '更新失败' : '创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleCouponDelete = async (id: number) => {
    try {
      await api.delete(`/operate/coupon/${id}`);
      message.success('已删除');
      fetchCoupons();
    } catch { message.error('删除失败'); }
  };

  const openCreateBatch = () => {
    batchForm.resetFields();
    batchForm.setFieldsValue({
      coupon_id: coupons[0]?.id || 0,
      quantity: 100,
      batch_name: '批量发放',
    });
    setBatchModalOpen(true);
  };

  const handleBatchSubmit = async (values: any) => {
    setSubmitting(true);
    try {
      const payload = {
        coupon_id: values.coupon_id,
        quantity: values.quantity,
        user_type: values.user_type,
        user_ids: values.user_ids,
        batch_name: values.batch_name,
      };
      await api.post('/operate/coupon/distribute', payload);
      message.success('发放成功');
      setBatchModalOpen(false);
      fetchCoupons(); // 更新库存
    } catch (e) {
      message.error('发放失败');
    } finally {
      setSubmitting(false);
    }
  };

  const couponColumns = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 150 },
    { title: '类型', dataIndex: 'coupon_type', key: 'coupon_type', width: 110,
      render: (v: string) => <Tag color={COUPON_TYPE_MAP[v]?.color || 'default'}>{COUPON_TYPE_MAP[v]?.text || v}</Tag> },
    { title: '面额/折扣', dataIndex: 'face_value', key: 'face_value', width: 100,
      render: (v: number, r: Coupon) => r.coupon_type === 'percentage' ? `${(v * 100).toFixed(0)}%` : `¥${v.toFixed(2)}` },
    { title: '门槛/上限', dataIndex: 'min_order_amount', key: 'min_order_amount', width: 120,
      render: (v: number, r: Coupon) => `≥¥${v.toFixed(2)}${r.max_discount_amount ? ` / ≤¥${r.max_discount_amount}` : ''}` },
    { title: '总库存', dataIndex: 'total_stock', key: 'total_stock', width: 80 },
    { title: '剩余', dataIndex: 'remaining_stock', key: 'remaining_stock', width: 80,
      render: (v: number) => <span style={{color: v > 0 ? '#34a853' : '#ea4335'}}>{v}</span> },
    { title: '每人限领', dataIndex: 'per_user_limit', key: 'per_user_limit', width: 90 },
    { title: '有效期(天)', dataIndex: 'valid_days', key: 'valid_days', width: 90 },
    { title: '发放时间', dataIndex: 'start_time', key: 'start_time', width: 140,
      render: (v: string) => new Date(v).toLocaleString('zh-CN') },
    { title: '截止时间', dataIndex: 'end_time', key: 'end_time', width: 140,
      render: (v: string) => new Date(v).toLocaleString('zh-CN') },
    { title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? '启用' : '停用'}</Tag> },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, record: Coupon) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditCoupon(record)}>编辑</Button>
          <Button size="small" icon={<GiftOutlined />} onClick={() => openCreateBatch()} style={{marginLeft: -4}}>发放</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleCouponDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const batchColumns = [
    { title: '批次名称', dataIndex: 'batch_name', key: 'batch_name', width: 140 },
    { title: '优惠券', dataIndex: 'coupon_id', key: 'coupon_id', width: 100,
      render: (v: number) => { const c = coupons.find(x => x.id === v); return c ? <Tag color="blue">{c.name}</Tag> : `ID:${v}`; } },
    { title: '发放数量', dataIndex: 'quantity', key: 'quantity', width: 90 },
    { title: '目标用户类型', dataIndex: 'user_type', key: 'user_type', width: 120,
      render: (v: string) => v ? <Tag color="blue">{USER_TYPE_MAP[v] || v}</Tag> : '全部' },
    { title: '指定用户', dataIndex: 'user_ids', key: 'user_ids', width: 150, render: (v: string) => v || '全部' },
    { title: '发放时间', dataIndex: 'distributed_at', key: 'distributed_at', width: 150,
      render: (v: string) => new Date(v).toLocaleString('zh-CN') },
  ];

  const usageColumns = [
    { title: '券码', dataIndex: 'coupon_code', key: 'coupon_code', width: 160, render: (v: string) => <code>{v}</code> },
    { title: '用户ID', dataIndex: 'user_id', key: 'user_id', width: 90 },
    { title: '用户类型', dataIndex: 'user_type', key: 'user_type', width: 110, render: (v: string) => <Tag color="blue">{USER_TYPE_MAP[v] || v}</Tag> },
    { title: '订单ID', dataIndex: 'order_id', key: 'order_id', width: 90, render: (v: number) => v ? v.toString() : '-' },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: (v: string) => <Tag color={STATUS_MAP[v]?.color || 'default'}>{STATUS_MAP[v]?.text || v}</Tag> },
    { title: '抵扣金额', dataIndex: 'discount_amount', key: 'discount_amount', width: 100, render: (v: number) => v ? `¥${v.toFixed(2)}` : '-' },
    { title: '领取时间', dataIndex: 'received_at', key: 'received_at', width: 150, render: (v: string) => new Date(v).toLocaleString('zh-CN') },
    { title: '使用时间', dataIndex: 'used_at', key: 'used_at', width: 150, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
    { title: '过期时间', dataIndex: 'expires_at', key: 'expires_at', width: 150, render: (v: string) => new Date(v).toLocaleString('zh-CN') },
  ];

      const statCards = [
    <Col xs={12} sm={6} key="1"><Card><Statistic title="优惠券总数" value={stats.total_coupons || 0} prefix={<GiftOutlined />} /></Card></Col>,
    <Col xs={12} sm={6} key="2"><Card><Statistic title="总库存" value={stats.total_stock || 0} /></Card></Col>,
    <Col xs={12} sm={6} key="3"><Card><Statistic title="剩余库存" value={stats.remaining_stock || 0} valueStyle={{ color: '#faad14' }} /></Card></Col>,
    <Col xs={12} sm={6} key="4"><Card><Statistic title="已发放" value={stats.total_distributed || 0} prefix={<CheckCircleOutlined />} /></Card></Col>,
    <Col xs={12} sm={6} key="5"><Card><Statistic title="已核销" value={stats.total_used || 0} prefix={<CheckCircleOutlined />} /></Card></Col>,
    <Col xs={12} sm={6} key="6"><Card><Statistic title="核销率" value={`${stats.usage_rate || 0}%`} valueStyle={{ color: '#1890ff' }} /></Card></Col>,
    <Col xs={12} sm={6} key="7"><Card><Statistic title="累计抵扣" value={stats.total_discount_amount || 0} precision={2} prefix={<DollarOutlined />} /></Card></Col>,
  ];

  return (
    <PageWrapper
      loading={couponLoading}
      skeletonType="table"
      skeletonCount={5}
      hasData={coupons.length > 0 || batches.length > 0 || usages.length > 0}
      empty={{ type: 'default', title: '暂无数据', description: '尚未创建优惠券', actionText: '刷新', onAction: () => { fetchCoupons(); fetchBatches(); fetchUsages(); fetchStats(); } }}
      onRetry={() => { fetchCoupons(); fetchBatches(); fetchUsages(); fetchStats(); }}
      transition="slide-up"
    >
      <div className="page-container">
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>{statCards}</Row>

        <Card extra={
          <Space>
            <Input placeholder="搜索优惠券名称" prefix={<SearchOutlined />} value={searchText} onChange={e => setSearchText(e.target.value)} style={{ width: 200 }} allowClear />
            <Button icon={<ReloadOutlined />} onClick={() => { fetchCoupons(); fetchBatches(); fetchUsages(); fetchStats(); }}>刷新</Button>
            {activeTab === 'coupons' && <Button type="primary" icon={<PlusOutlined />} onClick={openCreateCoupon}>新建优惠券</Button>}
            {activeTab === 'batches' && <Button type="primary" icon={<PlusOutlined />} onClick={openCreateBatch}>批量发放</Button>}
          </Space>
        }>
          <Tabs
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key as typeof activeTab)}
            items={[
              { key: 'coupons', label: <span><GiftOutlined /> 优惠券管理 ({coupons.length})</span>,
                children: <Table columns={couponColumns} dataSource={coupons} rowKey="id" loading={couponLoading} pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }} /> },
              { key: 'batches', label: <span><FileTextOutlined /> 发放批次 ({batches.length})</span>,
                children: <Table columns={batchColumns} dataSource={batches} rowKey="id" loading={batchLoading} pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }} /> },
              { key: 'usages', label: <span><CheckCircleOutlined /> 核销记录 ({usages.length})</span>,
                children: <Table columns={usageColumns} dataSource={usages} rowKey="id" loading={usageLoading} pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }} /> },
              { key: 'stats', label: <span><BarChartOutlined /> 统计概览</span>,
                children: <div style={{padding: 24}}>统计数据已在上方卡片展示</div> },
            ]}
          />
        </Card>

        {/* 优惠券弹窗 */}
        <Modal
          title={editingCoupon ? '编辑优惠券' : '新建优惠券'}
          open={couponModalOpen}
          onCancel={() => setCouponModalOpen(false)}
          onOk={() => couponForm.validateFields().then(handleCouponSubmit).catch(() => {})}
          confirmLoading={submitting}
          width={800}
          destroyOnHidden
        >
          <Form form={couponForm} layout="vertical" colon={false}>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="name" label="优惠券名称" rules={[{ required: true, message: '请输入名称' }]}>
                  <Input placeholder="请输入优惠券名称" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="coupon_type" label="券类型" rules={[{ required: true }]}>
                  <Select placeholder="选择券类型" options={[
                    { value: 'fixed', label: '固定金额券' },
                    { value: 'percentage', label: '百分比折扣券' },
                    { value: 'free_charge', label: '免单券' },
                    { value: 'service_free', label: '免服务费券' },
                  ]} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="face_value" label={couponForm.getFieldValue('coupon_type') === 'percentage' ? '折扣率 (0-1)' : '面额 (元)'} rules={[{ required: true }]}>
                  <InputNumber min={0} max={couponForm.getFieldValue('coupon_type') === 'percentage' ? 1 : 10000} step={couponForm.getFieldValue('coupon_type') === 'percentage' ? 0.01 : 0.01} precision={2} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="min_order_amount" label="最低使用门槛 (元)" rules={[{ required: true }]}>
                  <InputNumber min={0} step={0.01} precision={2} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="max_discount_amount" label="最大优惠金额上限 (元)">
                  <InputNumber min={0} step={0.01} precision={2} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="total_stock" label="总库存" rules={[{ required: true }]}>
                  <InputNumber min={0} step={1} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="per_user_limit" label="每人限领数量">
                  <InputNumber min={1} step={1} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="valid_days" label="领取后有效天数">
                  <InputNumber min={1} step={1} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="is_active" label="状态" valuePropName="checked">
                  <Switch checkedChildren="启用" unCheckedChildren="停用" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="start_time" label="发放开始时间" rules={[{ required: true }]}>
                  <DatePicker format="YYYY-MM-DD HH:mm:ss" placeholder="选择开始时间" showTime />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="end_time" label="发放结束时间" rules={[{ required: true }]}>
                  <DatePicker format="YYYY-MM-DD HH:mm:ss" placeholder="选择结束时间" showTime />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="applicable_user_types" label="适用用户类型 (逗号分隔, 留空为全部)">
                  <Input placeholder="如: app,card,vin,interconnect,enterprise" />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="applicable_stations" label="适用站点ID (逗号分隔, 留空为全部)">
                  <Input placeholder="如: 1,2,3" />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="description" label="描述">
                  <Input.TextArea rows={2} placeholder="优惠券描述" />
                </Form.Item>
              </Col>
            </Row>
          </Form>
        </Modal>

        {/* 发放批次弹窗 */}
        <Modal
          title="批量发放优惠券"
          open={batchModalOpen}
          onCancel={() => setBatchModalOpen(false)}
          onOk={() => batchForm.validateFields().then(handleBatchSubmit).catch(() => {})}
          confirmLoading={submitting}
          width={600}
          destroyOnHidden
        >
          <Form form={batchForm} layout="vertical" colon={false}>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="coupon_id" label="选择优惠券" rules={[{ required: true }]}>
                  <Select placeholder="选择优惠券" options={coupons.map(c => ({ value: c.id, label: c.name }))} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="quantity" label="发放数量" rules={[{ required: true }]}>
                  <InputNumber min={1} step={1} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="batch_name" label="批次名称">
                  <Input placeholder="如: 新用户首单券" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="user_type" label="目标用户类型">
                  <Select placeholder="选择用户类型" options={Object.entries(USER_TYPE_MAP).map(([v, l]) => ({ value: v, label: l }))} />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="user_ids" label="指定用户ID (逗号分隔, 留空为该类型全部)">
                  <Input placeholder="如: 1,2,3" />
                </Form.Item>
              </Col>
            </Row>
          </Form>
        </Modal>
      </div>
    </PageWrapper>
  );
};

export default CouponManagement;