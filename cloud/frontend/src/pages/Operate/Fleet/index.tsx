/**
 * 车队管理（Enterprise 实体）— 运营管理下的 Tab 页
 *
 * 列表：名称、编码、联系人、电话、余额、状态、创建时间
 * CRUD：创建（名称、编码、联系人、电话、描述）、编辑、删除
 * owner_team_id 自动填充为当前用户的 team_id
 * 场站绑定（卡691532f2）：绑定入口由车队设置页迁至此处，运营商为车队绑定可用场站
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Table, Button, Space, Tag, Tooltip, Popconfirm, Modal, Form,
  Input, InputNumber, Select, message,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, DeleteOutlined, EditOutlined, CarOutlined,
  EnvironmentOutlined,
} from '@ant-design/icons';
import { enterpriseAPI } from '../../../api';
import { getCurrentTeamId } from '../../../utils/team';

interface Enterprise {
  id: number;
  name: string;
  code: string;
  contact?: string;
  phone?: string;
  description?: string;
  balance?: number;
  status?: string;
  owner_team_id?: number;
  created_at?: string;
}

interface StationItem {
  id: number;
  name: string;
  code: string;
  address?: string;
  status?: string;
  team_id?: number;
}

const FleetManagement: React.FC = () => {
  const [enterprises, setEnterprises] = useState<Enterprise[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingEnterprise, setEditingEnterprise] = useState<Enterprise | null>(null);
  const [form] = Form.useForm();
  const [searchText, setSearchText] = useState('');
  // 场站绑定 Modal 状态（卡691532f2）
  const [bindingEnterprise, setBindingEnterprise] = useState<Enterprise | null>(null);
  const [bindingLoading, setBindingLoading] = useState(false);
  const [savingBinding, setSavingBinding] = useState(false);
  const [availableStations, setAvailableStations] = useState<StationItem[]>([]);
  const [selectedStationIds, setSelectedStationIds] = useState<number[]>([]);

  const fetchEnterprises = useCallback(async (keyword?: string) => {
    setLoading(true);
    try {
      const params: { keyword?: string } = {};
      if (keyword) params.keyword = keyword;
      const res = await enterpriseAPI.list(params);
      const data = res.data;
      const list = Array.isArray(data) ? data : (data?.items || data?.list || data?.data || []);
      setEnterprises(list);
    } catch (err) {
      message.error('车队列表加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEnterprises();
  }, [fetchEnterprises]);

  useEffect(() => {
    const timer = setTimeout(() => { fetchEnterprises(searchText); }, 300);
    return () => clearTimeout(timer);
  }, [searchText, fetchEnterprises]);

  const openCreate = () => {
    setEditingEnterprise(null);
    form.resetFields();
    setModalVisible(true);
  };

  const openEdit = (record: Enterprise) => {
    setEditingEnterprise(record);
    form.setFieldsValue(record);
    setModalVisible(true);
  };

  /* ── 场站绑定（卡691532f2：运营商为车队绑定可用场站） ── */
  const openBinding = async (record: Enterprise) => {
    setBindingEnterprise(record);
    setSelectedStationIds([]);
    setAvailableStations([]);
    setBindingLoading(true);
    try {
      const [boundRes, availRes] = await Promise.all([
        enterpriseAPI.stations(record.id),
        enterpriseAPI.availableStations(record.id),
      ]);
      const bound: StationItem[] = boundRes.data?.data || [];
      setAvailableStations(availRes.data?.data || []);
      setSelectedStationIds(bound.map(s => s.id));
    } catch {
      message.error('场站绑定信息加载失败');
    } finally {
      setBindingLoading(false);
    }
  };

  const handleSaveBinding = async () => {
    if (!bindingEnterprise) return;
    try {
      setSavingBinding(true);
      await enterpriseAPI.setStations(bindingEnterprise.id, selectedStationIds);
      message.success('场站绑定已更新');
      setBindingEnterprise(null);
    } catch (err: any) {
      message.error('场站绑定失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setSavingBinding(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await enterpriseAPI.delete(id);
      message.success('删除成功');
      fetchEnterprises(searchText);
    } catch (err) {
      message.error('删除失败');
    }
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      // owner_team_id 自动填充为当前用户的 team_id
      values.owner_team_id = getCurrentTeamId();
      try {
        if (editingEnterprise) {
          await enterpriseAPI.update(editingEnterprise.id, values);
          message.success('更新成功');
        } else {
          await enterpriseAPI.create(values);
          message.success('创建成功');
        }
        setModalVisible(false);
        form.resetFields();
        setEditingEnterprise(null);
        fetchEnterprises(searchText);
      } catch {
        message.error(editingEnterprise ? '更新失败' : '创建失败');
      }
    } catch {
      // 表单校验失败由 antd 字段提示覆盖
    }
  };

  const columns = [
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (name: string) => <span><CarOutlined style={{ marginRight: 6 }} />{name}</span>,
    },
    { title: '编码', dataIndex: 'code', key: 'code', width: 120 },
    { title: '联系人', dataIndex: 'contact', key: 'contact', width: 100 },
    { title: '电话', dataIndex: 'phone', key: 'phone', width: 130 },
    {
      title: '余额', dataIndex: 'balance', key: 'balance', width: 100,
      render: (balance: number) => balance != null ? `¥${balance.toFixed(2)}` : '-',
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (s: string) => {
        const colorMap: Record<string, string> = { active: 'green', disabled: 'red', suspended: 'orange' };
        const textMap: Record<string, string> = { active: '正常', disabled: '禁用', suspended: '暂停' };
        return <Tag color={colorMap[s] || 'default'}>{textMap[s] || s || '-'}</Tag>;
      },
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170,
      render: (d: string) => d || '-',
    },
    {
      title: '操作', key: 'action', width: 170,
      render: (_: unknown, record: Enterprise) => (
        <Space size="small">
          <Tooltip title="编辑"><Button icon={<EditOutlined />} size="small" onClick={() => openEdit(record)} /></Tooltip>
          <Tooltip title="场站绑定"><Button icon={<EnvironmentOutlined />} size="small" onClick={() => openBinding(record)} /></Tooltip>
          <Popconfirm title="确认删除该车队？" onConfirm={() => handleDelete(record.id)}>
            <Button icon={<DeleteOutlined />} size="small" danger />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16, flexWrap: 'wrap' }}>
        <Input.Search
          placeholder="搜索车队名称/编码"
          allowClear
          onSearch={setSearchText}
          style={{ width: 250 }}
        />
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增车队</Button>
        <Button icon={<ReloadOutlined />} onClick={() => fetchEnterprises(searchText)}>刷新</Button>
      </Space>
      <Table
        dataSource={enterprises}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 10 }}
      />

      {/* 新增/编辑 Modal */}
      <Modal
        title={editingEnterprise ? '编辑车队' : '新增车队'}
        open={modalVisible}
        onCancel={() => { setModalVisible(false); setEditingEnterprise(null); }}
        onOk={handleSave}
        width={560}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="车队名称" rules={[{ required: true, message: '请输入车队名称' }]}>
            <Input placeholder="请输入车队名称" />
          </Form.Item>
          <Form.Item name="code" label="车队编码" rules={[{ required: true, message: '请输入车队编码' }]}>
            <Input placeholder="请输入车队编码（如 FLEET-001）" />
          </Form.Item>
          <Form.Item name="contact" label="联系人">
            <Input placeholder="联系人姓名" />
          </Form.Item>
          <Form.Item name="phone" label="联系电话">
            <Input placeholder="联系电话" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="车队描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 场站绑定 Modal（卡691532f2：写入口迁至运维侧） */}
      <Modal
        title={bindingEnterprise ? `场站绑定 — ${bindingEnterprise.name}` : '场站绑定'}
        open={!!bindingEnterprise}
        onCancel={() => setBindingEnterprise(null)}
        onOk={handleSaveBinding}
        confirmLoading={savingBinding}
        okText="保存绑定"
        width={560}
      >
        <Select
          mode="multiple"
          style={{ width: '100%' }}
          loading={bindingLoading}
          placeholder="选择绑定的场站"
          value={selectedStationIds}
          onChange={(vals: number[]) => setSelectedStationIds(vals)}
          options={availableStations.map(s => ({ value: s.id, label: `${s.name} (${s.code})` }))}
          optionFilterProp="label"
        />
      </Modal>
    </>
  );
};

export default FleetManagement;
