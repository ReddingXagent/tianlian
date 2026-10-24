/**
 * 天链 V3 — 发票抬头管理页
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Table, Tag, Button, Space, Modal, Form, Input, Select, Switch, Popconfirm, message } from 'antd';
import { ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { invoiceTitleAPI } from '../../../api/settlement';

interface TitleItem {
  id: number;
  title_type: string;
  title_name: string;
  tax_id: string | null;
  register_address: string | null;
  register_phone: string | null;
  bank_name: string | null;
  bank_account: string | null;
  email: string | null;
  is_default: boolean;
}

const InvoiceTitlesPage: React.FC = () => {
  const [data, setData] = useState<TitleItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<TitleItem | null>(null);
  const [form] = Form.useForm();

  const loadData = useCallback(async (p = page) => {
    setLoading(true);
    try {
      const { data: res } = await invoiceTitleAPI.list({ page: p, page_size: 20 });
      const d = (res as any)?.data ?? res;
      setData(d?.items ?? []);
      setTotal(d?.total ?? 0);
    } catch {
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleAdd = () => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleEdit = (r: TitleItem) => {
    setEditing(r);
    form.setFieldsValue(r);
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const vals = await form.validateFields();
      if (editing) {
        await invoiceTitleAPI.update(editing.id, vals);
        message.success('抬头已更新');
      } else {
        await invoiceTitleAPI.create(vals);
        message.success('抬头已创建');
      }
      setModalOpen(false);
      loadData();
    } catch {
      message.error('操作失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await invoiceTitleAPI.delete(id);
      message.success('已删除');
      loadData();
    } catch {
      message.error('删除失败');
    }
  };

  const columns = [
    { title: '类型', dataIndex: 'title_type', key: 'title_type', width: 80, render: (v: string) => <Tag color={v === 'enterprise' ? 'blue' : 'default'}>{v === 'enterprise' ? '企业' : '个人'}</Tag> },
    { title: '抬头名称', dataIndex: 'title_name', key: 'title_name', width: 220 },
    { title: '税号', dataIndex: 'tax_id', key: 'tax_id', width: 180 },
    { title: '注册电话', dataIndex: 'register_phone', key: 'register_phone', width: 120 },
    { title: '开户银行', dataIndex: 'bank_name', key: 'bank_name', width: 160 },
    { title: '银行账号', dataIndex: 'bank_account', key: 'bank_account', width: 160 },
    { title: '邮箱', dataIndex: 'email', key: 'email', width: 180 },
    { title: '默认', dataIndex: 'is_default', key: 'is_default', width: 60, render: (v: boolean) => v ? <Tag color="green">默认</Tag> : '-' },
    {
      title: '操作', key: 'action', width: 100,
      render: (_: unknown, r: TitleItem) => (
        <Space size="small">
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => handleEdit(r)}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(r.id)}>
            <Button size="small" type="link" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadData()}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增抬头</Button>
        </Space>
      </div>

      <Table columns={columns} dataSource={data} rowKey="id" loading={loading} size="small"
        pagination={{ current: page, total, pageSize: 20, onChange: (p) => { setPage(p); loadData(p); } }}
      />

      <Modal title={editing ? '编辑抬头' : '新增抬头'} open={modalOpen} onOk={handleSubmit} onCancel={() => setModalOpen(false)} width={560}>
        <Form form={form} layout="vertical">
          <Form.Item name="title_type" label="抬头类型" rules={[{ required: true }]}>
            <Select options={[{ value: 'personal', label: '个人' }, { value: 'enterprise', label: '企业' }]} />
          </Form.Item>
          <Form.Item name="title_name" label="抬头名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="tax_id" label="纳税人识别号"><Input /></Form.Item>
          <Form.Item name="register_address" label="注册地址"><Input /></Form.Item>
          <Form.Item name="register_phone" label="注册电话"><Input /></Form.Item>
          <Form.Item name="bank_name" label="开户银行"><Input /></Form.Item>
          <Form.Item name="bank_account" label="银行账号"><Input /></Form.Item>
          <Form.Item name="email" label="接收邮箱"><Input /></Form.Item>
          <Form.Item name="is_default" label="设为默认" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default InvoiceTitlesPage;
