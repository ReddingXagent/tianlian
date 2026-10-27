/**
 * 天链V3 - 设备库（公共服务）
 * 设备模板库：设备类型、型号、厂商、参数模板
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Table, Card, Button, Space, Tag, Modal, Form, Input, Select, message, Row, Col, Statistic } from 'antd';
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined, AppstoreOutlined } from '@ant-design/icons';
import { deviceLibraryAPI } from '../../api';

const categoryMap: Record<string, { color: string; icon: string; label: string }> = {
  inverter: { color: '#722ed1', icon: '🔄', label: '逆变器' },
  storage: { color: '#ff5a36', icon: '🔋', label: '储能' },
  charger: { color: '#34a853', icon: '⚡', label: '充电桩' },
  solar: { color: '#f5a623', icon: '☀️', label: '光伏' },
  transformer: { color: '#eb2f96', icon: '🔌', label: '变压器' },
  meter: { color: '#13c2c2', icon: '📊', label: '电表' },
  sensor: { color: '#fa541c', icon: '🌡️', label: '传感器' },
};

const DeviceLibraryPage: React.FC = () => {
  const [devices, setDevices] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<string | undefined>(undefined);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [form] = Form.useForm();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { page, page_size: pageSize };
      if (categoryFilter) params.type = categoryFilter;
      if (searchKeyword) params.keyword = searchKeyword;
      const res = await deviceLibraryAPI.list(params);
      const d = (res.data as any)?.data;
      setDevices(d?.items || []);
      setTotal(d?.total || 0);
    } catch (e) {
      message.error('加载设备库失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, categoryFilter, searchKeyword]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleDelete = async (id: number) => {
    try {
      await deviceLibraryAPI.delete(id);
      message.success('已删除');
      fetchData();
    } catch { message.error('删除失败'); }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editing) {
        await deviceLibraryAPI.update(editing.id, values);
        message.success('已更新');
      } else {
        await deviceLibraryAPI.create(values);
        message.success('已创建');
      }
      setModalVisible(false);
      form.resetFields();
      fetchData();
    } catch { message.error('操作失败'); }
  };

  const columns = [
    { title: '设备名称', dataIndex: 'name', key: 'name' },
    {
      title: '类型', dataIndex: 'type', key: 'type', width: 120,
      render: (t: string) => {
        const info = categoryMap[t] || { color: 'default', icon: '📦', label: t };
        return <Tag color={info.color}>{info.icon} {info.label}</Tag>;
      },
    },
    { title: '型号', dataIndex: 'model', key: 'model' },
    { title: '厂商', dataIndex: 'manufacturer', key: 'manufacturer' },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s === 'active' ? '启用' : s}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: any, record: any) => (
        <Space size="small">
          <Button icon={<EditOutlined />} size="small" onClick={() => {
            setEditing(record);
            form.setFieldsValue(record);
            setModalVisible(true);
          }} />
          <Button icon={<DeleteOutlined />} size="small" danger onClick={() => handleDelete(record.id)} />
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Card size="small" style={{ cursor: 'pointer' }} onClick={() => { setCategoryFilter(undefined); setPage(1); }}>
            <Statistic title="总设备模板" value={total} prefix={<AppstoreOutlined />} />
          </Card>
        </Col>
        {Object.entries(categoryMap).map(([key, val]) => (
          <Col span={4} key={key}>
            <Card size="small" style={{ cursor: 'pointer', border: categoryFilter === key ? '2px solid #ff5a36' : undefined }}
              onClick={() => { setCategoryFilter(categoryFilter === key ? undefined : key); setPage(1); }}>
              <Statistic title={`${val.icon} ${val.label}`} value={devices.filter(d => d.type === key).length} />
            </Card>
          </Col>
        ))}
      </Row>

      <Card>
        <Space style={{ marginBottom: 16 }}>
          <Select value={categoryFilter} onChange={v => { setCategoryFilter(v); setPage(1); }} style={{ width: 150 }} allowClear placeholder="全部类型">
            {Object.entries(categoryMap).map(([key, val]) => (
              <Select.Option key={key} value={key}>{val.icon} {val.label}</Select.Option>
            ))}
          </Select>
          <Input.Search placeholder="搜索设备名称/型号/厂商" style={{ width: 250 }} onSearch={v => { setSearchKeyword(v); setPage(1); }} allowClear />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setModalVisible(true); }}>新增模板</Button>
          <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
        </Space>
        <Table dataSource={devices} columns={columns} rowKey="id"
          loading={loading}
          pagination={{ current: page, pageSize, total, showSizeChanger: true, onChange: (p, ps) => { setPage(p); setPageSize(ps); } }}
        />
      </Card>

      <Modal title={editing ? '编辑模板' : '新增模板'} open={modalVisible} onCancel={() => setModalVisible(false)} onOk={handleSubmit} width={600}>
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}><Form.Item name="name" label="设备名称" rules={[{ required: true, message: '请输入设备名称' }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="type" label="类型" rules={[{ required: true, message: '请选择类型' }]}>
              <Select>{Object.entries(categoryMap).map(([k, v]) => <Select.Option key={k} value={k}>{v.icon} {v.label}</Select.Option>)}</Select>
            </Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="model" label="型号"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="manufacturer" label="厂商"><Input /></Form.Item></Col>
          </Row>
          <Form.Item name="description" label="描述"><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default DeviceLibraryPage;
