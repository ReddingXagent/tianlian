/**
 * 天链 V3 - 积分管理页面
 * P0 运营核心补齐：积分规则CRUD、积分流水、统计
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Space, Input, InputNumber, Select, message, Popconfirm,
  Modal, Form, Switch, Row, Col, Statistic, Tabs, DatePicker,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, SearchOutlined,
  GoldOutlined, FileTextOutlined, BarChartOutlined, GiftOutlined,
} from '@ant-design/icons';
import api from '../../api';
import { fetchAllPages } from '../../api/fetchAll';
import PageWrapper from '../../components/PageWrapper';

/* ── 类型定义 ── */
interface PointsRule {
  id: number;
  name: string;
  rule_type: 'charge' | 'recharge' | 'sign_in' | 'invite' | 'birthday' | 'activity' | 'system';
  points: number;
  unit?: string;
  daily_limit?: number;
  weekly_limit?: number;
  total_limit?: number;
  applicable_user_types?: string;
  min_amount?: number;
  points_expire_days?: number;
  is_active: boolean;
  start_time?: string;
  end_time?: string;
  description?: string;
  created_at: string;
  updated_at: string;
}

interface PointsRecord {
  id: number;
  user_id: number;
  user_type?: string;
  rule_id?: number;
  record_type: 'earn' | 'redeem' | 'expire' | 'adjust';
  points: number;
  balance_before: number;
  balance_after: number;
  description?: string;
  order_id?: number;
  expires_at?: string;
  created_at: string;
}

const RULE_TYPE_MAP: Record<string, { color: string; text: string }> = {
  charge: { color: 'blue', text: '充电积分' },
  recharge: { color: 'purple', text: '充值积分' },
  sign_in: { color: 'green', text: '签到积分' },
  invite: { color: 'orange', text: '邀请积分' },
  birthday: { color: 'magenta', text: '生日积分' },
  activity: { color: 'gold', text: '活动积分' },
  system: { color: 'cyan', text: '系统发放' },
};

const RECORD_TYPE_MAP: Record<string, { color: string; text: string; icon: any }> = {
  earn: { color: 'green', text: '获取', icon: GoldOutlined },
  redeem: { color: 'red', text: '消费/兑换', icon: GiftOutlined },
  expire: { color: 'orange', text: '过期', icon: BarChartOutlined },
  adjust: { color: 'blue', text: '调整', icon: FileTextOutlined },
};

const USER_TYPE_MAP: Record<string, string> = {
  app: 'APP用户',
  card: '卡用户',
  vin: 'VIN用户',
  interconnect: '互联互通用户',
  enterprise: '企业用户',
};

/* ── 组件 ── */
const PointsManagement: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'rules' | 'records' | 'stats'>('rules');
  const [rules, setRules] = useState<PointsRule[]>([]);
  const [records, setRecords] = useState<PointsRecord[]>([]);
  const [stats, setStats] = useState<any>({});
  const [ruleLoading, setRuleLoading] = useState(false);
  const [recordLoading, setRecordLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<PointsRule | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [form] = Form.useForm();

  const fetchRules = useCallback(async () => {
    setRuleLoading(true);
    try {
      const extra: Record<string, unknown> = {};
      if (searchText) extra.search = searchText;
      const items = await fetchAllPages<PointsRule>((params) => api.get('/operate/points', { params }), extra);
      setRules(items);
    } catch { message.error('加载积分规则失败'); }
    finally { setRuleLoading(false); }
  }, [searchText]);

  const fetchRecords = useCallback(async () => {
    setRecordLoading(true);
    try {
      const items = await fetchAllPages<PointsRecord>((params) => api.get('/operate/points/records', { params }));
      setRecords(items);
    } catch { message.error('加载积分流水失败'); setRecords([]); }
    finally { setRecordLoading(false); }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const res = await api.get('/operate/points/stats');
      setStats(res.data || {});
    } catch { }
  }, []);

  useEffect(() => {
    fetchRules();
    fetchRecords();
    fetchStats();
  }, [fetchRules, fetchRecords, fetchStats]);

  const openCreate = () => {
    setEditingRule(null);
    form.resetFields();
    form.setFieldsValue({
      rule_type: 'charge',
      points: 1,
      is_active: true,
    });
    setModalOpen(true);
  };

  const openEdit = (record: PointsRule) => {
    setEditingRule(record);
    form.setFieldsValue({
      name: record.name,
      rule_type: record.rule_type,
      points: record.points,
      unit: record.unit || '',
      daily_limit: record.daily_limit || '',
      weekly_limit: record.weekly_limit || '',
      total_limit: record.total_limit || '',
      applicable_user_types: record.applicable_user_types || '',
      min_amount: record.min_amount || '',
      points_expire_days: record.points_expire_days || '',
      is_active: record.is_active,
      description: record.description || '',
      start_time: record.start_time ? new Date(record.start_time) : null,
      end_time: record.end_time ? new Date(record.end_time) : null,
    });
    setModalOpen(true);
  };

  const handleSubmit = async (values: any) => {
    setSubmitting(true);
    try {
      const payload = {
        ...values,
        start_time: values.start_time?.toISOString(),
        end_time: values.end_time?.toISOString(),
        applicable_user_types: values.applicable_user_types || undefined,
        daily_limit: values.daily_limit || undefined,
        weekly_limit: values.weekly_limit || undefined,
        total_limit: values.total_limit || undefined,
        min_amount: values.min_amount || undefined,
        points_expire_days: values.points_expire_days || undefined,
      };
      if (editingRule) {
        await api.put(`/operate/points/${editingRule.id}`, payload);
        message.success('更新成功');
      } else {
        await api.post('/operate/points', payload);
        message.success('创建成功');
      }
      setModalOpen(false);
      fetchRules();
    } catch (e) {
      message.error(editingRule ? '更新失败' : '创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/operate/points/${id}`);
      message.success('已删除');
      fetchRules();
    } catch { message.error('删除失败'); }
  };

  const ruleColumns = [
    { title: '规则名称', dataIndex: 'name', key: 'name', width: 140 },
    { title: '类型', dataIndex: 'rule_type', key: 'rule_type', width: 110,
      render: (v: string) => <Tag color={RULE_TYPE_MAP[v]?.color || 'default'}>{RULE_TYPE_MAP[v]?.text || v}</Tag> },
    { title: '积分值', dataIndex: 'points', key: 'points', width: 80,
      render: (v: number, r: PointsRule) => `${v} ${r.unit ? `/${r.unit}` : ''}` },
    { title: '每日上限', dataIndex: 'daily_limit', key: 'daily_limit', width: 90, render: (v: number) => v ? `${v}/天` : '无' },
    { title: '每周上限', dataIndex: 'weekly_limit', key: 'weekly_limit', width: 90, render: (v: number) => v ? `${v}/周` : '无' },
    { title: '总上限', dataIndex: 'total_limit', key: 'total_limit', width: 90, render: (v: number) => v ? `${v}/总` : '无' },
    { title: '适用用户', dataIndex: 'applicable_user_types', key: 'applicable_user_types', width: 150,
      render: (v: string) => v ? v.split(',').map(u => <Tag key={u} color="blue" style={{marginRight: 4}}>{USER_TYPE_MAP[u] || u}</Tag>) : '全部' },
    { title: '最低触发', dataIndex: 'min_amount', key: 'min_amount', width: 100,
      render: (v: number) => v ? `¥${v}` : '无' },
    { title: '积分过期(天)', dataIndex: 'points_expire_days', key: 'points_expire_days', width: 100, render: (v: number) => v ? `${v}天` : '永久' },
    { title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? '启用' : '停用'}</Tag> },
    { title: '生效时间', dataIndex: 'start_time', key: 'start_time', width: 140, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '立即' },
    { title: '失效时间', dataIndex: 'end_time', key: 'end_time', width: 140, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '长期' },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: unknown, record: PointsRule) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const recordColumns = [
    { title: '用户ID', dataIndex: 'user_id', key: 'user_id', width: 90 },
    { title: '用户类型', dataIndex: 'user_type', key: 'user_type', width: 110, render: (v: string) => <Tag color="blue">{USER_TYPE_MAP[v] || v}</Tag> },
    { title: '规则', dataIndex: 'rule_id', key: 'rule_id', width: 80, render: (v: number) => v ? <Tag color="blue">{v}</Tag> : '-' },
    { title: '类型', dataIndex: 'record_type', key: 'record_type', width: 100,
      render: (v: string) => {
        const m = RECORD_TYPE_MAP[v];
        return m ? <Tag color={m.color}><m.icon style={{marginRight: 4}} />{m.text}</Tag> : <Tag>{v}</Tag>;
      } },
    { title: '积分变动', dataIndex: 'points', key: 'points', width: 100,
      render: (v: number) => <span style={{color: v > 0 ? '#34a853' : '#ea4335', fontWeight: 600}}>{v > 0 ? '+' : ''}{v}</span> },
    { title: '变动前', dataIndex: 'balance_before', key: 'balance_before', width: 90 },
    { title: '变动后', dataIndex: 'balance_after', key: 'balance_after', width: 90 },
    { title: '备注', dataIndex: 'description', key: 'description', width: 150 },
    { title: '关联订单', dataIndex: 'order_id', key: 'order_id', width: 90, render: (v: number) => v ? v.toString() : '-' },
    { title: '过期时间', dataIndex: 'expires_at', key: 'expires_at', width: 150, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 150, render: (v: string) => new Date(v).toLocaleString('zh-CN') },
  ];

  const statCards = [
    <Col xs={12} sm={6} key="1"><Card><Statistic title="规则总数" value={stats.total_rules || 0} prefix={<GoldOutlined />} /></Card></Col>,
    <Col xs={12} sm={6} key="2"><Card><Statistic title="活跃规则" value={stats.active_rules || 0} valueStyle={{ color: '#34a853' }} /></Card></Col>,
    <Col xs={12} sm={6} key="3"><Card><Statistic title="累计获取" value={stats.total_earned || 0} prefix={<GoldOutlined />} /></Card></Col>,
    <Col xs={12} sm={6} key="4"><Card><Statistic title="流水总数" value={stats.total_records || 0} prefix={<FileTextOutlined />} /></Card></Col>,
  ];

  return (
    <PageWrapper
      loading={ruleLoading}
      skeletonType="table"
      skeletonCount={5}
      hasData={rules.length > 0 || records.length > 0}
      empty={{ type: 'default', title: '暂无数据', description: '尚未配置积分规则', actionText: '刷新', onAction: () => { fetchRules(); fetchRecords(); fetchStats(); } }}
      onRetry={() => { fetchRules(); fetchRecords(); fetchStats(); }}
      transition="slide-up"
    >
      <div className="page-container">
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>{statCards}</Row>

        <Card extra={
          <Space>
            <Input placeholder="搜索规则名称" prefix={<SearchOutlined />} value={searchText} onChange={e => setSearchText(e.target.value)} style={{ width: 200 }} allowClear />
            <Button icon={<ReloadOutlined />} onClick={() => { fetchRules(); fetchRecords(); fetchStats(); }}>刷新</Button>
            {activeTab === 'rules' && <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建积分规则</Button>}
          </Space>
        }>
          <Tabs
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key as typeof activeTab)}
            items={[
              { key: 'rules', label: <span><GoldOutlined style={{marginRight: 4}} />积分规则 ({rules.length})</span>,
                children: <Table columns={ruleColumns} dataSource={rules} rowKey="id" loading={ruleLoading} pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }} /> },
              { key: 'records', label: <span><FileTextOutlined style={{marginRight: 4}} />积分流水 ({records.length})</span>,
                children: <Table columns={recordColumns} dataSource={records} rowKey="id" loading={recordLoading} pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }} /> },
              { key: 'stats', label: <span><BarChartOutlined style={{marginRight: 4}} />统计概览</span>,
                children: <div style={{padding: 24}}>统计数据已在上方卡片展示</div> },
            ]}
          />
        </Card>

        {/* 积分规则弹窗 */}
        <Modal
          title={editingRule ? '编辑积分规则' : '新建积分规则'}
          open={modalOpen}
          onCancel={() => setModalOpen(false)}
          onOk={() => form.validateFields().then(handleSubmit).catch(() => {})}
          confirmLoading={submitting}
          width={800}
          destroyOnHidden
        >
          <Form form={form} layout="vertical" colon={false}>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="name" label="规则名称" rules={[{ required: true, message: '请输入名称' }]}>
                  <Input placeholder="请输入规则名称" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="rule_type" label="规则类型" rules={[{ required: true }]}>
                  <Select placeholder="选择规则类型" options={[
                    { value: 'charge', label: '充电积分' },
                    { value: 'recharge', label: '充值积分' },
                    { value: 'sign_in', label: '签到积分' },
                    { value: 'invite', label: '邀请积分' },
                    { value: 'birthday', label: '生日积分' },
                    { value: 'activity', label: '活动积分' },
                    { value: 'system', label: '系统发放' },
                  ]} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="points" label="积分值" rules={[{ required: true }]}>
                  <InputNumber min={0} step={1} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="unit" label="积分单位描述">
                  <Input placeholder="如: 每消费1元, 每充电1kWh" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="daily_limit" label="每日上限">
                  <InputNumber min={0} step={1} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="weekly_limit" label="每周上限">
                  <InputNumber min={0} step={1} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="total_limit" label="总上限">
                  <InputNumber min={0} step={1} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="min_amount" label="最低触发金额 (元)">
                  <InputNumber min={0} step={0.01} precision={2} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="points_expire_days" label="积分过期天数">
                  <InputNumber min={1000000} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="is_active" label="状态" valuePropName="checked">
                  <Switch checkedChildren="启用" unCheckedChildren="停用" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="start_time" label="规则生效开始时间">
                  <DatePicker showTime placeholder="选择开始时间" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="end_time" label="规则生效结束时间">
                  <DatePicker showTime placeholder="选择结束时间" />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="applicable_user_types" label="适用用户类型 (逗号分隔, 留空为全部)">
                  <Input placeholder="如: app,card,vin,interconnect,enterprise" />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="description" label="规则描述">
                  <Input.TextArea rows={2} placeholder="积分规则描述" />
                </Form.Item>
              </Col>
            </Row>
          </Form>
        </Modal>
      </div>
    </PageWrapper>
  );
};

export default PointsManagement;