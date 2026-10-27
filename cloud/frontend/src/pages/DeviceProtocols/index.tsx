/**
 * 天链V3 - 设备协议管理（公共服务）
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Table, Card, Button, Space, Tag, Modal, Form, Input, Select, InputNumber, message, Row, Col, Statistic } from 'antd';
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { protocolAPI } from '../../api';

const typeColorMap: Record<string, string> = {
  modbus_tcp: 'blue', modbus_rtu: 'geekblue', mqtt: 'green', ocpp: 'purple',
  iec104: 'orange', opcua: 'magenta', dlt645: 'default',
};
const typeLabelMap: Record<string, string> = {
  modbus_tcp: 'Modbus TCP', modbus_rtu: 'Modbus RTU', mqtt: 'MQTT', ocpp: 'OCPP',
  iec104: 'IEC 104', opcua: 'OPC-UA', dlt645: 'DL/T 645',
};

const DeviceProtocolsPage: React.FC = () => {
  const [protocols, setProtocols] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [form] = Form.useForm();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { page, page_size: pageSize };
      if (searchKeyword) params.keyword = searchKeyword;
      const res = await protocolAPI.list(params);
      const d = (res.data as any)?.data;
      setProtocols(d?.items || []);
      setTotal(d?.total || 0);
    } catch (e) {
      message.error('加载协议列表失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, searchKeyword]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleDelete = async (id: number) => {
    try {
      await protocolAPI.delete(id);
      message.success('已删除');
      fetchData();
    } catch { message.error('删除失败'); }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editing) {
        await protocolAPI.update(editing.id, values);
        message.success('已更新');
      } else {
        await protocolAPI.create(values);
        message.success('已创建');
      }
      setModalVisible(false);
      form.resetFields();
      fetchData();
    } catch { message.error('操作失败'); }
  };

  const columns = [
    { title: '协议名称', dataIndex: 'name', key: 'name' },
    {
      title: '类型', dataIndex: 'type', key: 'type', width: 130,
      render: (t: string) => <Tag color={typeColorMap[t] || 'default'}>{typeLabelMap[t] || t}</Tag>,
    },
    { title: '版本', dataIndex: 'version', key: 'version', width: 80 },
    { title: '端口', dataIndex: 'port', key: 'port', width: 80 },
    { title: '波特率', dataIndex: 'baud_rate', key: 'baud_rate', width: 80 },
    { title: '数据位', dataIndex: 'data_bits', key: 'data_bits', width: 70 },
    { title: '停止位', dataIndex: 'stop_bits', key: 'stop_bits', width: 70 },
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
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={12} lg={6}><Card><Statistic title="总协议数" value={total} /></Card></Col>
        <Col xs={12} sm={12} lg={6}><Card><Statistic title="已启用" value={protocols.filter(p => p.status === 'active').length} valueStyle={{ color: '#34a853' }} /></Card></Col>
        <Col xs={12} sm={12} lg={6}><Card><Statistic title="协议类型" value={new Set(protocols.map(p => p.type)).size} /></Card></Col>
        <Col xs={12} sm={12} lg={6}><Card><Statistic title="串口协议" value={protocols.filter(p => p.baud_rate).length} /></Card></Col>
      </Row>

      <Card>
        <Space style={{ marginBottom: 16 }} wrap>
          <Input.Search placeholder="搜索协议名称/类型" style={{ width: 200 }} onSearch={v => { setSearchKeyword(v); setPage(1); }} allowClear />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setModalVisible(true); }}>新增协议</Button>
          <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
        </Space>
        <div className="table-scroll-x">
          <Table dataSource={protocols} columns={columns} rowKey="id"
            loading={loading}
            pagination={{ current: page, pageSize, total, showSizeChanger: true, onChange: (p, ps) => { setPage(p); setPageSize(ps); } }}
          />
        </div>
      </Card>

      <Modal title={editing ? '编辑协议' : '新增协议'} open={modalVisible} onCancel={() => setModalVisible(false)} onOk={handleSubmit} width={600}>
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}><Form.Item name="name" label="协议名称" rules={[{ required: true, message: '请输入协议名称' }]}><Input /></Form.Item></Col>
            <Col span={12}>
              <Form.Item name="type" label="协议类型" rules={[{ required: true, message: '请选择类型' }]}>
                <Select>
                  {Object.entries(typeLabelMap).map(([k, v]) => <Select.Option key={k} value={k}>{v}</Select.Option>)}
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}><Form.Item name="version" label="版本"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="port" label="端口"><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="baud_rate" label="波特率"><InputNumber style={{ width: '100%' }} /></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}><Form.Item name="data_bits" label="数据位" initialValue={8}><InputNumber min={5} max={9} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="stop_bits" label="停止位" initialValue={1}><InputNumber min={1} max={2} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="parity" label="校验" initialValue="none">
              <Select><Select.Option value="none">无</Select.Option><Select.Option value="even">偶校验</Select.Option><Select.Option value="odd">奇校验</Select.Option></Select>
            </Form.Item></Col>
          </Row>
          <Form.Item name="description" label="描述"><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default DeviceProtocolsPage;
