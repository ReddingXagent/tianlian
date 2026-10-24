/**
 * 天链 V3 - 折扣管理页面
 * P0 运营核心补齐：折扣方案 + 折扣电价组管理
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Space, Input, InputNumber, Select, message, Popconfirm,
  Modal, Form, Switch, Row, Col, Statistic, Tabs, DatePicker,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, SearchOutlined,
  DollarOutlined, TeamOutlined, SettingOutlined,
} from '@ant-design/icons';
import api from '../../api';
import { fetchAllPages } from '../../api/fetchAll';
import PageWrapper from '../../components/PageWrapper';

/* ── 类型定义 ── */
interface PriceDiscount {
  id: number;
  name: string;
  discount_type: 'percentage' | 'fixed' | 'tiered';
  discount_rate: number;
  applicable_user_types?: string;
  min_consumption: number;
  max_discount_amount?: number;
  start_time: string;
  end_time: string;
  priority: number;
  is_active: boolean;
  description?: string;
  created_at: string;
  updated_at: string;
}

interface DiscountGroup {
  id: number;
  name: string;
  discount_id: number;
  user_type: string;
  user_ids?: string;
  station_ids?: string;
  priority: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const DISCOUNT_TYPE_MAP: Record<string, { color: string; text: string }> = {
  percentage: { color: 'blue', text: '百分比折扣' },
  fixed: { color: 'green', text: '固定金额' },
  tiered: { color: 'orange', text: '阶梯折扣' },
};

const USER_TYPE_MAP: Record<string, string> = {
  app: 'APP用户',
  card: '卡用户',
  vin: 'VIN用户',
  interconnect: '互联互通用户',
  enterprise: '企业用户',
};

/* ── 组件 ── */
const DiscountManagement: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'discounts' | 'groups'>('discounts');
  const [discounts, setDiscounts] = useState<PriceDiscount[]>([]);
  const [groups, setGroups] = useState<DiscountGroup[]>([]);
  const [discountLoading, setDiscountLoading] = useState(false);
  const [groupLoading, setGroupLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [discountModalOpen, setDiscountModalOpen] = useState(false);
  const [groupModalOpen, setGroupModalOpen] = useState(false);
  const [editingDiscount, setEditingDiscount] = useState<PriceDiscount | null>(null);
  const [editingGroup, setEditingGroup] = useState<DiscountGroup | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [discountForm] = Form.useForm();
  const [groupForm] = Form.useForm();

  const fetchDiscounts = useCallback(async () => {
    setDiscountLoading(true);
    try {
      const extra: Record<string, unknown> = {};
      if (searchText) extra.search = searchText;
      const items = await fetchAllPages<PriceDiscount>((params) => api.get('/operate/discount', { params }), extra);
      setDiscounts(items);
    } catch (e) {
      message.error('加载折扣方案失败');
    } finally {
      setDiscountLoading(false);
    }
  }, [searchText]);

  const fetchGroups = useCallback(async () => {
    setGroupLoading(true);
    try {
      const items = await fetchAllPages<DiscountGroup>((params) => api.get('/operate/discount/groups', { params }));
      setGroups(items);
    } catch (e) {
      message.error('加载折扣组失败');
    } finally {
      setGroupLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDiscounts();
    fetchGroups();
  }, [fetchDiscounts, fetchGroups]);

  const openCreateDiscount = () => {
    setEditingDiscount(null);
    discountForm.resetFields();
    discountForm.setFieldsValue({
      discount_type: 'percentage',
      discount_rate: 0.9,
      min_consumption: 0,
      priority: 0,
      is_active: true,
      start_time: new Date(),
      end_time: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000),
    });
    setDiscountModalOpen(true);
  };

  const openEditDiscount = (record: PriceDiscount) => {
    setEditingDiscount(record);
    discountForm.setFieldsValue({
      name: record.name,
      discount_type: record.discount_type,
      discount_rate: record.discount_rate,
      applicable_user_types: record.applicable_user_types || '',
      min_consumption: record.min_consumption,
      max_discount_amount: record.max_discount_amount || '',
      priority: record.priority,
      is_active: record.is_active,
      description: record.description || '',
      start_time: new Date(record.start_time),
      end_time: new Date(record.end_time),
    });
    setDiscountModalOpen(true);
  };

  const handleDiscountSubmit = async (values: any) => {
    setSubmitting(true);
    try {
      const payload = {
        ...values,
        start_time: values.start_time?.toISOString(),
        end_time: values.end_time?.toISOString(),
        applicable_user_types: values.applicable_user_types || undefined,
        max_discount_amount: values.max_discount_amount || undefined,
      };
      if (editingDiscount) {
        await api.put(`/operate/discount/${editingDiscount.id}`, payload);
        message.success('更新成功');
      } else {
        await api.post('/operate/discount', payload);
        message.success('创建成功');
      }
      setDiscountModalOpen(false);
      fetchDiscounts();
    } catch (e) {
      message.error(editingDiscount ? '更新失败' : '创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDiscountDelete = async (id: number) => {
    try {
      await api.delete(`/operate/discount/${id}`);
      message.success('已删除');
      fetchDiscounts();
    } catch { message.error('删除失败'); }
  };

  const openCreateGroup = () => {
    setEditingGroup(null);
    groupForm.resetFields();
    groupForm.setFieldsValue({ discount_id: discounts[0]?.id || 0, user_type: 'app', priority: 0, is_active: true });
    setGroupModalOpen(true);
  };

  const openEditGroup = (record: DiscountGroup) => {
    setEditingGroup(record);
    groupForm.setFieldsValue({
      name: record.name,
      discount_id: record.discount_id,
      user_type: record.user_type,
      user_ids: record.user_ids || '',
      station_ids: record.station_ids || '',
      priority: record.priority,
      is_active: record.is_active,
    });
    setGroupModalOpen(true);
  };

  const handleGroupSubmit = async (values: any) => {
    setSubmitting(true);
    try {
      const payload = { ...values };
      if (editingGroup) {
        await api.put(`/operate/discount/group/${editingGroup.id}`, payload);
        message.success('更新成功');
      } else {
        await api.post('/operate/discount/group', payload);
        message.success('创建成功');
      }
      setGroupModalOpen(false);
      fetchGroups();
    } catch (e) {
      message.error(editingGroup ? '更新失败' : '创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleGroupDelete = async (id: number) => {
    try {
      await api.delete(`/operate/discount/group/${id}`);
      message.success('已删除');
      fetchGroups();
    } catch { message.error('删除失败'); }
  };

  const discountColumns = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 140 },
    { title: '类型', dataIndex: 'discount_type', key: 'discount_type', width: 110,
      render: (v: string) => <Tag color={DISCOUNT_TYPE_MAP[v]?.color || 'default'}>{DISCOUNT_TYPE_MAP[v]?.text || v}</Tag> },
    { title: '折扣率/金额', dataIndex: 'discount_rate', key: 'discount_rate', width: 100,
      render: (v: number) => v < 1 ? `${(v * 100).toFixed(0)}%` : `¥${v.toFixed(2)}` },
    { title: '适用用户类型', dataIndex: 'applicable_user_types', key: 'applicable_user_types', width: 160,
      render: (v: string) => v ? v.split(',').map(t => USER_TYPE_MAP[t.trim()] || t.trim()).join(', ') : '全部' },
    { title: '最低消费', dataIndex: 'min_consumption', key: 'min_consumption', width: 90,
      render: (v: number) => `¥${v.toFixed(2)}` },
    { title: '最大减免', dataIndex: 'max_discount_amount', key: 'max_discount_amount', width: 90,
      render: (v: number) => v ? `¥${v.toFixed(2)}` : '无上限' },
    { title: '生效时间', dataIndex: 'start_time', key: 'start_time', width: 140,
      render: (v: string) => new Date(v).toLocaleString('zh-CN') },
    { title: '失效时间', dataIndex: 'end_time', key: 'end_time', width: 140,
      render: (v: string) => new Date(v).toLocaleString('zh-CN') },
    { title: '优先级', dataIndex: 'priority', key: 'priority', width: 70 },
    { title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? '启用' : '停用'}</Tag> },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: unknown, record: PriceDiscount) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditDiscount(record)}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDiscountDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const groupColumns = [
    { title: '分组名称', dataIndex: 'name', key: 'name', width: 140 },
    { title: '关联折扣', dataIndex: 'discount_id', key: 'discount_id', width: 100,
      render: (v: number) => {
        const d = discounts.find(x => x.id === v);
        return d ? <Tag color="blue">{d.name}</Tag> : `ID:${v}`;
      } },
    { title: '用户类型', dataIndex: 'user_type', key: 'user_type', width: 120,
      render: (v: string) => <Tag color="blue">{USER_TYPE_MAP[v] || v}</Tag> },
    { title: '指定用户', dataIndex: 'user_ids', key: 'user_ids', width: 120,
      render: (v: string) => v ? <span style={{fontSize: 12}}>{v}</span> : '全部' },
    { title: '指定站点', dataIndex: 'station_ids', key: 'station_ids', width: 120,
      render: (v: string) => v ? <span style={{fontSize: 12}}>{v}</span> : '全部' },
    { title: '优先级', dataIndex: 'priority', key: 'priority', width: 70 },
    { title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? '启用' : '停用'}</Tag> },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: unknown, record: DiscountGroup) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditGroup(record)}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleGroupDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageWrapper
      loading={discountLoading || groupLoading}
      skeletonType="table"
      skeletonCount={5}
      hasData={discounts.length > 0 || groups.length > 0}
      empty={{ type: 'default', title: '暂无数据', description: '尚未配置折扣方案', actionText: '刷新', onAction: () => { fetchDiscounts(); fetchGroups(); } }}
      onRetry={() => { fetchDiscounts(); fetchGroups(); }}
      transition="slide-up"
    >
      <div className="page-container">
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}>
            <Card><Statistic title="折扣方案总数" value={discounts.length} prefix={<DollarOutlined />} /></Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card><Statistic title="折扣组总数" value={groups.length} prefix={<TeamOutlined />} /></Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card><Statistic title="启用中" value={discounts.filter(d => d.is_active).length} valueStyle={{ color: '#34a853' }} /></Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card><Statistic title="停用中" value={discounts.filter(d => !d.is_active).length} valueStyle={{ color: '#faad14' }} /></Card>
          </Col>
        </Row>

        <Card
          extra={
            <Space>
              <Input placeholder="搜索折扣名称" prefix={<SearchOutlined />} value={searchText} onChange={e => setSearchText(e.target.value)} style={{ width: 200 }} allowClear />
              <Button icon={<ReloadOutlined />} onClick={() => { fetchDiscounts(); fetchGroups(); }}>刷新</Button>
              {activeTab === 'discounts' ? (
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreateDiscount}>新建折扣方案</Button>
              ) : (
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreateGroup}>新建折扣组</Button>
              )}
            </Space>
          }
        >
          <Tabs
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key as typeof activeTab)}
            items={[
              {
                key: 'discounts',
                label: <span><DollarOutlined style={{marginRight: 4}} />折扣方案 ({discounts.length})</span>,
                children: (
                  <Table
                    columns={discountColumns}
                    dataSource={discounts}
                    rowKey="id"
                    loading={discountLoading}
                    pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (total: number) => `共 ${total} 条` }}
                  />
                ),
              },
              {
                key: 'groups',
                label: <span><TeamOutlined style={{marginRight: 4}} />折扣电价组 ({groups.length})</span>,
                children: (
                  <Table
                    columns={groupColumns}
                    dataSource={groups}
                    rowKey="id"
                    loading={groupLoading}
                    pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (total: number) => `共 ${total} 条` }}
                  />
                ),
              },
            ]}
          />
        </Card>

        {/* 折扣方案弹窗 */}
        <Modal
          title={editingDiscount ? '编辑折扣方案' : '新建折扣方案'}
          open={discountModalOpen}
          onCancel={() => setDiscountModalOpen(false)}
          onOk={() => discountForm.validateFields().then(handleDiscountSubmit).catch(() => {})}
          confirmLoading={submitting}
          width={800}
          destroyOnHidden
        >
          <Form form={discountForm} layout="vertical" colon={false}>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="name" label="折扣名称" rules={[{ required: true, message: '请输入名称' }]}>
                  <Input placeholder="请输入折扣名称" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="discount_type" label="折扣类型" rules={[{ required: true }]}>
                  <Select placeholder="选择折扣类型" options={[
                    { value: 'percentage', label: '百分比折扣 (如0.9=9折)' },
                    { value: 'fixed', label: '固定金额折扣' },
                    { value: 'tiered', label: '阶梯折扣' },
                  ]} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="discount_rate" label={discountForm.getFieldValue('discount_type') === 'percentage' ? '折扣率 (0-1)' : '固定金额 (元)'} rules={[{ required: true }]}>
                  <InputNumber
                    min={0}
                    max={discountForm.getFieldValue('discount_type') === 'percentage' ? 1 : 10000}
                    step={discountForm.getFieldValue('discount_type') === 'percentage' ? 0.01 : 0.01}
                    precision={2}
                  />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="min_consumption" label="最低消费门槛 (元)" rules={[{ required: true }]}>
                  <InputNumber min={0} step={0.01} precision={2} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="max_discount_amount" label="最大折扣金额上限 (元)">
                  <InputNumber min={0} step={0.01} precision={2} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="priority" label="优先级">
                  <InputNumber min={0} step={1} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="is_active" label="状态" valuePropName="checked">
                  <Switch checkedChildren="启用" unCheckedChildren="停用" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="start_time" label="生效开始时间" rules={[{ required: true }]}>
                  <DatePicker format="YYYY-MM-DD HH:mm:ss" placeholder="选择开始时间" showTime />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="end_time" label="生效结束时间" rules={[{ required: true }]}>
                  <DatePicker format="YYYY-MM-DD HH:mm:ss" placeholder="选择结束时间" showTime />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="applicable_user_types" label="适用用户类型 (逗号分隔, 留空为全部)">
                  <Input placeholder="如: app,card,vin,interconnect,enterprise" />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="description" label="描述">
                  <Input.TextArea rows={2} placeholder="折扣方案描述" />
                </Form.Item>
              </Col>
            </Row>
          </Form>
        </Modal>

        {/* 折扣组弹窗 */}
        <Modal
          title={editingGroup ? '编辑折扣组' : '新建折扣组'}
          open={groupModalOpen}
          onCancel={() => setGroupModalOpen(false)}
          onOk={() => groupForm.validateFields().then(handleGroupSubmit).catch(() => {})}
          confirmLoading={submitting}
          width={600}
          destroyOnHidden
        >
          <Form form={groupForm} layout="vertical" colon={false}>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="name" label="分组名称" rules={[{ required: true, message: '请输入名称' }]}>
                  <Input placeholder="请输入分组名称" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="discount_id" label="关联折扣方案" rules={[{ required: true }]}>
                  <Select placeholder="选择折扣方案" options={discounts.map(d => ({ value: d.id, label: d.name }))} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="user_type" label="用户类型" rules={[{ required: true }]}>
                  <Select placeholder="选择用户类型" options={Object.entries(USER_TYPE_MAP).map(([v, l]) => ({ value: v, label: l }))} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="priority" label="优先级">
                  <InputNumber min={0} step={1} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="is_active" label="状态" valuePropName="checked">
                  <Switch checkedChildren="启用" unCheckedChildren="停用" />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="user_ids" label="指定用户ID (逗号分隔, 留空为该类型全部)">
                  <Input placeholder="如: 1,2,3" />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="station_ids" label="适用站点ID (逗号分隔, 留空为全部)">
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

export default DiscountManagement;