/**
 * 天链 V3 - 停车管理页面
 * Phase46：商户站点停车折扣方案管理
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Space, Input, InputNumber, Select, message, Popconfirm,
  Modal, Form, Switch, Row, Col, Statistic,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, SearchOutlined,
  CarOutlined, CheckCircleOutlined, StopOutlined,
} from '@ant-design/icons';
import api from '../../api';
import PageWrapper from '../../components/PageWrapper';

interface ParkingDiscount {
  id: number;
  station_id: number;
  merchant_name?: string;
  discount_type: string;
  free_minutes?: number;
  discount_percent?: number;
  fixed_amount?: number;
  max_discount?: number | null;
  valid_start?: string;
  valid_end?: string;
  is_active: boolean;
  remark?: string;
  created_at?: string;
}

const TYPE_MAP: Record<string, { color: string; text: string }> = {
  free_minutes: { color: 'blue', text: '免费时长' },
  percentage: { color: 'gold', text: '折扣比例' },
  fixed: { color: 'green', text: '固定减免' },
};

const ParkingManagement: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<ParkingDiscount[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [keyword, setKeyword] = useState('');
  const [activeFilter, setActiveFilter] = useState<boolean | undefined>(undefined);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ParkingDiscount | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (keyword) params.keyword = keyword;
      if (activeFilter !== undefined) params.is_active = activeFilter;
      const res = await api.get('/parking/discounts', { params });
      const data = res.data?.items || res.data || [];
      setItems(data);
      setTotal(res.data?.total ?? data.length);
    } catch {
      message.error('加载停车折扣方案失败');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, keyword, activeFilter]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ discount_type: 'free_minutes', free_minutes: 0, discount_percent: 0, fixed_amount: 0, is_active: true });
    setModalOpen(true);
  };

  const openEdit = (record: ParkingDiscount) => {
    setEditing(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      if (editing) {
        await api.put(`/parking/discounts/${editing.id}`, values);
        message.success('更新成功');
      } else {
        await api.post('/parking/discounts', values);
        message.success('创建成功');
      }
      setModalOpen(false);
      fetchData();
    } catch (err: any) {
      if (err?.errorFields) return; // 表单校验错误
      message.error(err?.response?.data?.detail || '操作失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/parking/discounts/${id}`);
      message.success('已删除');
      fetchData();
    } catch {
      message.error('删除失败');
    }
  };

  const activeCount = items.filter(i => i.is_active).length;

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: '商户站点', dataIndex: 'station_id', width: 100, render: (v: number, r: ParkingDiscount) => `${v} ${r.merchant_name ? '/ ' + r.merchant_name : ''}` },
    {
      title: '折扣类型', dataIndex: 'discount_type', width: 110,
      render: (v: string) => <Tag color={TYPE_MAP[v]?.color || 'default'}>{TYPE_MAP[v]?.text || v}</Tag>,
    },
    {
      title: '折扣详情', key: 'detail',
      render: (_: unknown, r: ParkingDiscount) => {
        if (r.discount_type === 'free_minutes') return `免费 ${r.free_minutes ?? 0} 分钟`;
        if (r.discount_type === 'percentage') return `${r.discount_percent ?? 0}% 折扣`;
        return `减免 ${r.fixed_amount ?? 0} 元`;
      },
    },
    { title: '有效时段', key: 'valid', render: (_: unknown, r: ParkingDiscount) => r.valid_start ? `${r.valid_start} - ${r.valid_end || ''}` : '全天' },
    { title: '单次上限', dataIndex: 'max_discount', width: 100, render: (v: number | null) => v != null ? `¥${v}` : '-' },
    {
      title: '状态', dataIndex: 'is_active', width: 90,
      render: (v: boolean) => v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>,
    },
    {
      title: '操作', key: 'action', width: 140, fixed: 'right' as const,
      render: (_: unknown, r: ParkingDiscount) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
          <Popconfirm title="确认删除该折扣方案？" onConfirm={() => handleDelete(r.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageWrapper loading={loading} hasData={items.length > 0} skeletonType="table">
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><Statistic title="折扣方案总数" value={total} prefix={<CarOutlined />} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="启用中" value={activeCount} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="已停用" value={total - activeCount} prefix={<StopOutlined />} valueStyle={{ color: '#bfbfbf' }} /></Card></Col>
      </Row>

      <Card
        title="停车折扣方案管理"
        extra={
          <Space>
            <Input.Search
              placeholder="搜索商户名称"
              allowClear
              style={{ width: 200 }}
              onSearch={(v) => { setKeyword(v); setPage(1); }}
            />
            <Select
              placeholder="状态筛选"
              allowClear
              style={{ width: 120 }}
              onChange={(v) => { setActiveFilter(v); setPage(1); }}
              options={[{ value: true, label: '启用' }, { value: false, label: '停用' }]}
            />
            <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增方案</Button>
          </Space>
        }
      >
        <Table
          rowKey="id"
          dataSource={items}
          columns={columns}
          loading={loading}
          scroll={{ x: 900 }}
          pagination={{
            current: page, pageSize, total,
            showSizeChanger: true,
            onChange: (p, ps) => { setPage(p); setPageSize(ps); },
          }}
        />
      </Card>

      <Modal
        title={editing ? '编辑停车折扣方案' : '新增停车折扣方案'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={submitting}
        destroyOnHidden
        width={560}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="station_id" label="商户站点ID" rules={[{ required: true, message: '请输入站点ID' }]}>
            <InputNumber style={{ width: '100%' }} min={1} />
          </Form.Item>
          <Form.Item name="merchant_name" label="商户名称">
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item name="discount_type" label="折扣类型" rules={[{ required: true }]}>
            <Select options={Object.entries(TYPE_MAP).map(([k, v]) => ({ value: k, label: v.text }))} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="free_minutes" label="免费时长(分钟)"><InputNumber style={{ width: '100%' }} min={0} /></Form.Item></Col>
            <Col span={12}><Form.Item name="discount_percent" label="折扣比例(%)"><InputNumber style={{ width: '100%' }} min={0} max={100} /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="fixed_amount" label="固定减免(元)"><InputNumber style={{ width: '100%' }} min={0} /></Form.Item></Col>
            <Col span={12}><Form.Item name="max_discount" label="单次最大减免(元)"><InputNumber style={{ width: '100%' }} min={0} /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="valid_start" label="每日开始(HH:MM)"><Input placeholder="如 08:00" /></Form.Item></Col>
            <Col span={12}><Form.Item name="valid_end" label="每日结束(HH:MM)"><Input placeholder="如 22:00" /></Form.Item></Col>
          </Row>
          <Form.Item name="is_active" label="启用" valuePropName="checked"><Switch /></Form.Item>
          <Form.Item name="remark" label="备注"><Input.TextArea maxLength={500} rows={2} /></Form.Item>
        </Form>
      </Modal>
    </PageWrapper>
  );
};

export default ParkingManagement;
