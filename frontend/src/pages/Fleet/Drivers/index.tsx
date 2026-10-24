/**
 * 车队 - 司机管理页面
 *
 * 功能：司机列表 / 创建 / 编辑 / 详情抽屉(含账户/交易)
 * API: /api/v1/fleet/drivers
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm, Statistic, Row, Col, Drawer, Descriptions, InputNumber,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  SearchOutlined, IdcardOutlined, PhoneOutlined, UserOutlined,
  WalletOutlined, DollarOutlined,
} from '@ant-design/icons';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';

/* ── 类型 ── */
interface Driver {
  id: number;
  enterprise_id: number;
  name: string;
  phone: string;
  license_no: string;
  license_type?: string;
  assigned_vehicle_id?: number | null;
  hire_date?: string;
  status: string;
  total_charge_kwh?: number;
  total_spent?: number;
  rating?: number;
  account?: {
    id: number;
    balance: number;
    status: string;
  };
}

/* ── 常量 ── */
const STATUS_COLORS: Record<string, string> = {
  active: 'green', normal: 'green',
  inactive: 'red', suspended: 'orange',
};
const STATUS_TEXT: Record<string, string> = {
  active: '在职', normal: '正常',
  inactive: '离职', suspended: '停职',
};
const LICENSE_TYPES = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'];

/* ── 组件 ── */
const FleetDriversPage: React.FC = () => {
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Driver | null>(null);
  const [drawerDriver, setDrawerDriver] = useState<Driver | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [transactions, setTransactions] = useState<any[]>([]);
  const [txLoading, setTxLoading] = useState(false);
  const [rechargeModalOpen, setRechargeModalOpen] = useState(false);
  const [rechargeAmount, setRechargeAmount] = useState(0);
  const [form] = Form.useForm();

  const loadDrivers = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/fleet/drivers');
      const items = Array.isArray(data) ? data : (data as any)?.items || [];
      setDrivers(items);
    } catch {
      setDrivers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadDrivers(); }, [loadDrivers]);

  /* ── CRUD ── */
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editing) {
        await api.put(`/fleet/drivers/${editing.id}`, values);
        message.success('司机信息已更新');
      } else {
        await api.post('/fleet/drivers', values);
        message.success('司机已创建');
      }
      setModalOpen(false);
      form.resetFields();
      setEditing(null);
      loadDrivers();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/fleet/drivers/${id}`);
      message.success('已删除');
      loadDrivers();
    } catch (err: any) {
      message.error('删除失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  /* ── 详情抽屉 ── */
  const openDetail = async (driver: Driver) => {
    setDrawerDriver(driver);
    setDrawerOpen(true);
    setTxLoading(true);
    try {
      const { data } = await api.get(`/fleet/drivers/${driver.id}/transactions`);
      const items = Array.isArray(data) ? data : (data as any)?.items || [];
      setTransactions(items);
    } catch {
      setTransactions([]);
    } finally {
      setTxLoading(false);
    }
  };

  const handleRecharge = async () => {
    if (!drawerDriver || rechargeAmount <= 0) return;
    try {
      await api.post(`/fleet/drivers/${drawerDriver.id}/account/recharge`, {
        amount: rechargeAmount,
      });
      message.success('充值成功');
      setRechargeModalOpen(false);
      setRechargeAmount(0);
      // 刷新
      const { data: fresh } = await api.get(`/fleet/drivers/${drawerDriver.id}`);
      setDrawerDriver(fresh);
      const { data: txs } = await api.get(`/fleet/drivers/${drawerDriver.id}/transactions`);
      setTransactions(Array.isArray(txs) ? txs : (txs as any)?.items || []);
    } catch (err: any) {
      message.error('充值失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  /* ── 筛选 ── */
  const filtered = drivers.filter(
    d => !search || d.name?.toLowerCase().includes(search.toLowerCase())
      || d.phone?.includes(search) || d.license_no?.includes(search)
  );

  /* ── 统计 ── */
  const stats = {
    total: drivers.length,
    active: drivers.filter(d => d.status === 'active').length,
    totalSpent: drivers.reduce((s, d) => s + (d.total_spent || 0), 0),
    avgRating: drivers.length ? (drivers.reduce((s, d) => s + (d.rating || 5), 0) / drivers.length).toFixed(1) : '5.0',
  };

  const columns = [
    { title: '姓名', dataIndex: 'name', key: 'name', width: 90, render: (v: string, r: Driver) => (
      <a onClick={() => openDetail(r)}>{v}</a>
    )},
    { title: '电话', dataIndex: 'phone', key: 'phone', width: 120 },
    { title: '驾驶证号', dataIndex: 'license_no', key: 'license_no', width: 150 },
    { title: '驾照类型', dataIndex: 'license_type', key: 'license_type', width: 80, render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
    { title: '累计充电(kWh)', dataIndex: 'total_charge_kwh', key: 'total_charge_kwh', width: 120, align: 'right' as const, render: (v: number) => v?.toFixed(1) || '0.0' },
    { title: '累计消费(¥)', dataIndex: 'total_spent', key: 'total_spent', width: 110, align: 'right' as const, render: (v: number) => v?.toFixed(2) || '0.00' },
    { title: '评分', dataIndex: 'rating', key: 'rating', width: 70, align: 'right' as const, render: (v: number) => v?.toFixed(1) || '5.0' },
    { title: '状态', dataIndex: 'status', key: 'status', width: 80, render: (v: string) => <Tag color={STATUS_COLORS[v] || 'default'}>{STATUS_TEXT[v] || v}</Tag> },
    {
      title: '操作', key: 'action', width: 150,
      render: (_: unknown, r: Driver) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditing(r);
            form.setFieldsValue(r);
            setModalOpen(true);
          }}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageWrapper loading={loading && drivers.length === 0} skeletonType="table" hasData={drivers.length > 0}
      empty={{ type: 'default', title: '暂无司机', description: '点击新增添加司机', actionText: '新增司机', onAction: () => { setEditing(null); form.resetFields(); form.setFieldsValue({ status: 'active', license_type: 'C1' }); setModalOpen(true); }}}
      transition="slide-up"
    >
      <div className="page-container">
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}><Card><Statistic title="司机总数" value={stats.total} prefix={<IdcardOutlined />} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="在职" value={stats.active} valueStyle={{ color: '#52c41a' }} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="累计消费" value={stats.totalSpent} prefix="¥" precision={2} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="平均评分" value={stats.avgRating} prefix={<UserOutlined />} /></Card></Col>
        </Row>

        <Card extra={
          <Space>
            <Input placeholder="搜索姓名/电话/驾照" prefix={<SearchOutlined />} value={search} onChange={e => setSearch(e.target.value)} style={{ width: 220 }} allowClear />
            <Button icon={<ReloadOutlined />} onClick={loadDrivers}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); form.setFieldsValue({ status: 'active', license_type: 'C1' }); setModalOpen(true); }}>新增司机</Button>
          </Space>
        }>
          <Table columns={columns} dataSource={filtered} rowKey="id" loading={loading}
            pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
          />
        </Card>

        {/* 新增/编辑 Modal */}
        <Modal title={editing ? '编辑司机' : '新增司机'} open={modalOpen} onOk={handleSubmit}
          onCancel={() => { setModalOpen(false); form.resetFields(); setEditing(null); }}
          width={560} destroyOnHidden
        >
          <Form form={form} layout="vertical">
            <Row gutter={16}>
              <Col span={12}><Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}><Input prefix={<UserOutlined />} placeholder="司机姓名" /></Form.Item></Col>
              <Col span={12}><Form.Item name="phone" label="电话" rules={[{ required: true, message: '请输入电话' }]}><Input prefix={<PhoneOutlined />} placeholder="手机号" /></Form.Item></Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}><Form.Item name="license_no" label="驾驶证号" rules={[{ required: true, message: '请输入驾驶证号' }]}><Input placeholder="驾驶证号" /></Form.Item></Col>
              <Col span={12}><Form.Item name="license_type" label="驾照类型" initialValue="C1"><Select>{LICENSE_TYPES.map(t => <Select.Option key={t} value={t}>{t}</Select.Option>)}</Select></Form.Item></Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}><Form.Item name="enterprise_id" label="企业ID" rules={[{ required: true, message: '请输入企业ID' }]}><InputNumber style={{ width: '100%' }} placeholder="企业ID" min={1} /></Form.Item></Col>
              <Col span={12}><Form.Item name="status" label="状态" initialValue="active"><Select><Select.Option value="active">在职</Select.Option><Select.Option value="inactive">离职</Select.Option><Select.Option value="suspended">停职</Select.Option></Select></Form.Item></Col>
            </Row>
          </Form>
        </Modal>

        {/* 详情抽屉 */}
        <Drawer title={`司机详情 - ${drawerDriver?.name || ''}`} open={drawerOpen} width={560}
          onClose={() => { setDrawerOpen(false); setDrawerDriver(null); }}
        >
          {drawerDriver && (
            <>
              <Descriptions column={2} bordered size="small">
                <Descriptions.Item label="姓名">{drawerDriver.name}</Descriptions.Item>
                <Descriptions.Item label="电话">{drawerDriver.phone}</Descriptions.Item>
                <Descriptions.Item label="驾驶证号">{drawerDriver.license_no}</Descriptions.Item>
                <Descriptions.Item label="驾照类型">{drawerDriver.license_type || '-'}</Descriptions.Item>
                <Descriptions.Item label="状态"><Tag color={STATUS_COLORS[drawerDriver.status] || 'default'}>{STATUS_TEXT[drawerDriver.status] || drawerDriver.status}</Tag></Descriptions.Item>
                <Descriptions.Item label="入职日期">{drawerDriver.hire_date?.split('T')[0] || '-'}</Descriptions.Item>
                <Descriptions.Item label="累计充电(kWh)">{drawerDriver.total_charge_kwh?.toFixed(1) || '0.0'}</Descriptions.Item>
                <Descriptions.Item label="累计消费(¥)">{drawerDriver.total_spent?.toFixed(2) || '0.00'}</Descriptions.Item>
                <Descriptions.Item label="评分">{drawerDriver.rating?.toFixed(1) || '5.0'}</Descriptions.Item>
                <Descriptions.Item label="账户余额">
                  <span style={{ fontWeight: 600, color: drawerDriver.account?.balance > 0 ? '#52c41a' : '#999' }}>
                    ¥ {drawerDriver.account?.balance?.toFixed(2) || '0.00'}
                  </span>
                </Descriptions.Item>
              </Descriptions>
              <Space style={{ marginTop: 12 }}>
                <Button type="primary" icon={<WalletOutlined />} onClick={() => setRechargeModalOpen(true)}>充值</Button>
              </Space>

              <Card title="交易流水" size="small" style={{ marginTop: 16 }} loading={txLoading}>
                <Table dataSource={transactions} rowKey="id" size="small" pagination={{ pageSize: 5 }}
                  columns={[
                    { title: '类型', dataIndex: 'type', key: 'type', width: 80, render: (v: string) => <Tag color={v === 'recharge' ? 'green' : v === 'consume' ? 'orange' : 'blue'}>{v}</Tag> },
                    { title: '金额', dataIndex: 'amount', key: 'amount', width: 90, align: 'right' as const, render: (v: number) => `¥${v?.toFixed(2)}` },
                    { title: '余额', dataIndex: 'balance_after', key: 'balance_after', width: 90, align: 'right' as const, render: (v: number) => `¥${v?.toFixed(2)}` },
                    { title: '备注', dataIndex: 'remark', key: 'remark', ellipsis: true },
                    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 140, render: (v: string) => v?.split('T')[0] || '-' },
                  ]}
                />
              </Card>
            </>
          )}
        </Drawer>

        {/* 充值 Modal */}
        <Modal title="账户充值" open={rechargeModalOpen} onOk={handleRecharge}
          onCancel={() => { setRechargeModalOpen(false); setRechargeAmount(0); }}
        >
          <Form layout="vertical">
            <Form.Item label="充值金额(¥)">
              <InputNumber style={{ width: '100%' }} value={rechargeAmount} min={0.01} step={100} precision={2}
                onChange={v => setRechargeAmount(v || 0)} prefix={<DollarOutlined />}
              />
            </Form.Item>
          </Form>
        </Modal>
      </div>
    </PageWrapper>
  );
};

export default FleetDriversPage;
