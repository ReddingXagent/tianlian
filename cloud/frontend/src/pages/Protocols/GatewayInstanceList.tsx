/**
 * 天链V3 - 网关实例列表（协议实例CRUD）
 * 管理运行态的协议实例，含连接/断开操作
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Table, Card, Button, Space, Tag, Modal, Form, Input, Select, InputNumber,
  message, Row, Col, Statistic, Alert, Empty, Spin, Tooltip, Popconfirm
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined,
  PlayCircleOutlined, PauseCircleOutlined, ApiOutlined
} from '@ant-design/icons';
import { protocolInstanceAPI } from '../../api';
import type { ProtocolInstance } from '../../types';

const protocolTypeColorMap: Record<string, string> = {
  modbus_rtu: 'blue',
  modbus_tcp: 'geekblue',
  mqtt: 'green',
  rest: 'purple',
  ocpp: 'orange',
  iec104: 'magenta',
  dlt645: 'default',
};

const protocolTypeOptions = [
  { value: 'modbus_rtu', label: 'Modbus RTU' },
  { value: 'modbus_tcp', label: 'Modbus TCP' },
  { value: 'mqtt', label: 'MQTT' },
  { value: 'rest', label: 'REST API' },
  { value: 'ocpp', label: 'OCPP' },
  { value: 'iec104', label: 'IEC 104' },
  { value: 'opcua', label: 'OPC-UA' },
  { value: 'dlt645', label: 'DL/T 645' },
];

const GatewayInstanceList: React.FC = () => {
  const [instances, setInstances] = useState<ProtocolInstance[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<ProtocolInstance | null>(null);
  const [form] = Form.useForm();

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await protocolInstanceAPI.list({ page, page_size: pageSize });
      const d = (res.data as any)?.data;
      setInstances(d?.items || []);
      setTotal(d?.total || 0);
    } catch (err: unknown) {
      const msg = (err as any)?.response?.data?.message || (err as any)?.message || '加载失败';
      setError(msg);
      message.error('加载协议实例失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleConnect = async (id: number) => {
    try {
      await protocolInstanceAPI.connect(id);
      message.success('连接已建立');
      fetchData();
    } catch { message.error('连接失败'); }
  };

  const handleDisconnect = async (id: number) => {
    try {
      await protocolInstanceAPI.disconnect(id);
      message.success('连接已断开');
      fetchData();
    } catch { message.error('断开失败'); }
  };

  const handleDelete = async (id: number) => {
    try {
      await protocolInstanceAPI.delete(id);
      message.success('已删除');
      fetchData();
    } catch { message.error('删除失败'); }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editing) {
        await protocolInstanceAPI.update(editing.id, values);
        message.success('已更新');
      } else {
        await protocolInstanceAPI.create(values);
        message.success('已创建');
      }
      setModalVisible(false);
      form.resetFields();
      setEditing(null);
      fetchData();
    } catch { /* validation failed */ }
  };

  const statusTag = (status: string) => {
    const colorMap: Record<string, string> = { running: 'green', stopped: 'default', error: 'red' };
    const labelMap: Record<string, string> = { running: '运行中', stopped: '已停止', error: '错误' };
    return <Tag color={colorMap[status] || 'default'}>{labelMap[status] || status}</Tag>;
  };

  const connStatusTag = (status: string) => {
    const colorMap: Record<string, string> = { connected: 'green', disconnected: 'default', connecting: 'blue' };
    const labelMap: Record<string, string> = { connected: '已连接', disconnected: '未连接', connecting: '连接中' };
    return <Tag color={colorMap[status] || 'default'}>{labelMap[status] || status}</Tag>;
  };

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 150, ellipsis: true },
    {
      title: '协议类型', dataIndex: 'protocol_type', key: 'protocol_type', width: 120,
      render: (t: string) => {
        const opt = protocolTypeOptions.find(o => o.value === t);
        return <Tag color={protocolTypeColorMap[t] || 'default'}>{opt?.label || t}</Tag>;
      },
    },
    { title: '设备类型', dataIndex: 'device_type', key: 'device_type', width: 130, ellipsis: true, render: (v: string) => v || '-' },
    { title: '网关ID', dataIndex: 'gateway_id', key: 'gateway_id', width: 80, render: (v: number) => v ?? '-' },
    { title: '状态', dataIndex: 'status', key: 'status', width: 80, render: (s: string) => statusTag(s) },
    { title: '连接', dataIndex: 'connection_status', key: 'connection_status', width: 80, render: (s: string) => connStatusTag(s) },
    {
      title: '最后连接', dataIndex: 'last_connected', key: 'last_connected', width: 170,
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作', key: 'action', width: 200,
      render: (_: unknown, record: ProtocolInstance) => (
        <Space size="small">
          {record.connection_status === 'disconnected' ? (
            <Tooltip title="连接">
              <Button icon={<PlayCircleOutlined />} size="small" type="primary" ghost onClick={() => handleConnect(record.id)} />
            </Tooltip>
          ) : (
            <Tooltip title="断开">
              <Popconfirm title="确认断开连接?" onConfirm={() => handleDisconnect(record.id)}>
                <Button icon={<PauseCircleOutlined />} size="small" danger />
              </Popconfirm>
            </Tooltip>
          )}
          <Tooltip title="编辑">
            <Button icon={<EditOutlined />} size="small" onClick={() => {
              setEditing(record);
              form.setFieldsValue(record);
              setModalVisible(true);
            }} />
          </Tooltip>
          <Popconfirm title="确认删除?" description="删除后无法恢复" onConfirm={() => handleDelete(record.id)}>
            <Button icon={<DeleteOutlined />} size="small" danger />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><Statistic title="总实例" value={total} prefix={<ApiOutlined />} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="运行中" value={instances.filter(i => i.status === 'running').length} valueStyle={{ color: '#34a853' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="已连接" value={instances.filter(i => i.connection_status === 'connected').length} valueStyle={{ color: '#34a853' }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="错误" value={instances.filter(i => i.status === 'error').length} valueStyle={{ color: '#ea4335' }} /></Card></Col>
      </Row>

      {error && <Alert type="error" message={error} closable style={{ marginBottom: 16 }} />}

      <Card>
        <Space style={{ marginBottom: 16 }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setModalVisible(true); }}>
            新增实例
          </Button>
          <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
        </Space>
        <Spin spinning={loading}>
          <Table
            dataSource={instances}
            columns={columns}
            rowKey="id"
            pagination={{
              current: page, pageSize, total,
              showSizeChanger: true,
              showTotal: (t) => `共 ${t} 条`,
              onChange: (p, ps) => { setPage(p); setPageSize(ps); },
            }}
            locale={{ emptyText: <Empty description="暂无协议实例" /> }}
          />
        </Spin>
      </Card>

      {/* 新增/编辑弹窗 */}
      <Modal
        title={editing ? `编辑实例 - ${editing.name}` : '新增协议实例'}
        open={modalVisible}
        onCancel={() => { setModalVisible(false); form.resetFields(); setEditing(null); }}
        onOk={handleSubmit}
        width={600}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="实例名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如: 逆变器Modbus采集" />
          </Form.Item>
          <Form.Item name="protocol_type" label="协议类型" rules={[{ required: true, message: '请选择协议类型' }]}>
            <Select placeholder="选择协议类型">
              {protocolTypeOptions.map(o => <Select.Option key={o.value} value={o.value}>{o.label}</Select.Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="device_type" label="设备类型">
            <Select placeholder="选择设备类型" allowClear>
              <Select.Option value="inverter_eahi_20k">逆变器 EAHI5-20K</Select.Option>
              <Select.Option value="pcs_100kw">PCS 100kW</Select.Option>
              <Select.Option value="charger_dc_60kw">直流充电桩 60kW</Select.Option>
              <Select.Option value="meter_three_phase">三相电表</Select.Option>
              <Select.Option value="bms_lithium">锂电池BMS</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="gateway_id" label="关联网关ID">
            <InputNumber placeholder="可选" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="parser_schema" label="解析Schema">
            <Select placeholder="选择解析Schema" allowClear>
              <Select.Option value="modbus_inverter">Modbus 逆变器</Select.Option>
              <Select.Option value="mqtt_charger">MQTT 充电桩</Select.Option>
              <Select.Option value="rest_third_party">REST 第三方对接</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="可选描述" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default GatewayInstanceList;