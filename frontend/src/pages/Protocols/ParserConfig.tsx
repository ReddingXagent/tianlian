/**
 * 天链V3 - 解析器配置页面
 * 管理设备类型 → 协议适配器 → 解析Schema的映射配置
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Table, Card, Button, Space, Tag, Modal, Form, Input, Select, Switch,
  message, Row, Col, Statistic, Alert, Empty, Spin, Popconfirm
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined,
  FileTextOutlined
} from '@ant-design/icons';
import { parserConfigAPI } from '../../api';
import type { ParserConfig } from '../../types';

const protocolColorMap: Record<string, string> = {
  modbus_rtu: 'blue', modbus_tcp: 'geekblue',
  mqtt: 'green', rest: 'purple',
};

const ParserConfigPage: React.FC = () => {
  const [configs, setConfigs] = useState<ParserConfig[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<ParserConfig | null>(null);
  const [form] = Form.useForm();

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await parserConfigAPI.list({ page, page_size: pageSize });
      const d = (res.data as any)?.data;
      setConfigs(d?.items || []);
      setTotal(d?.total || 0);
    } catch (err: unknown) {
      const msg = (err as any)?.response?.data?.message || (err as any)?.message || '加载失败';
      setError(msg);
      message.error('加载解析器配置失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleToggleStatus = async (record: ParserConfig, checked: boolean) => {
    const next = checked ? 'active' : 'inactive';
    try {
      await parserConfigAPI.update(record.id, { status: next });
      message.success(checked ? '已启用' : '已停用');
      fetchData();
    } catch {
      message.error('切换状态失败');
    }
  };

  const handleDelete = async (id: number) => {
    try { await parserConfigAPI.delete(id); message.success('已删除'); fetchData(); }
    catch { message.error('删除失败'); }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editing) {
        await parserConfigAPI.update(editing.id, values);
        message.success('已更新');
      } else {
        await parserConfigAPI.create(values);
        message.success('已创建');
      }
      setModalVisible(false);
      form.resetFields();
      setEditing(null);
      fetchData();
    } catch { /* validation */ }
  };

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 150, ellipsis: true },
    { title: '设备类型', dataIndex: 'device_type', key: 'device_type', width: 150, ellipsis: true },
    {
      title: '协议', dataIndex: 'protocol', key: 'protocol', width: 100,
      render: (p: string) => <Tag color={protocolColorMap[p] || 'default'}>{p}</Tag>,
    },
    { title: '解析Schema', dataIndex: 'parser_schema', key: 'parser_schema', width: 130, render: (v: string) => v || '-' },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (s: string, record: ParserConfig) => (
        <Switch
          size="small"
          checked={s === 'active'}
          onChange={(checked) => handleToggleStatus(record, checked)}
          aria-label={`切换 ${record.name} 启用状态`}
        />
      ),
    },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true, render: (v: string) => v || '-' },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: unknown, record: ParserConfig) => (
        <Space size="small">
          <Button icon={<EditOutlined />} size="small" onClick={() => {
            setEditing(record);
            form.setFieldsValue(record);
            setModalVisible(true);
          }} />
          <Popconfirm title="确认删除?" onConfirm={() => handleDelete(record.id)}>
            <Button icon={<DeleteOutlined />} size="small" danger />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}><Card size="small"><Statistic title="总配置" value={total} prefix={<FileTextOutlined />} /></Card></Col>
        <Col span={8}><Card size="small"><Statistic title="已启用" value={configs.filter(c => c.status === 'active').length} valueStyle={{ color: '#34a853' }} /></Card></Col>
        <Col span={8}><Card size="small"><Statistic title="设备类型" value={new Set(configs.map(c => c.device_type)).size} /></Card></Col>
      </Row>

      {error && <Alert type="error" message={error} closable style={{ marginBottom: 16 }} />}

      <Card>
        <Space style={{ marginBottom: 16 }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setModalVisible(true); }}>
            新增解析器配置
          </Button>
          <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
        </Space>
        <Spin spinning={loading}>
          <Table
            dataSource={configs}
            columns={columns}
            rowKey="id"
            pagination={{
              current: page, pageSize, total,
              showSizeChanger: true,
              showTotal: (t) => `共 ${t} 条`,
              onChange: (p, ps) => { setPage(p); setPageSize(ps); },
            }}
            locale={{ emptyText: <Empty description="暂无解析器配置" /> }}
          />
        </Spin>
      </Card>

      <Modal
        title={editing ? `编辑解析器 - ${editing.name}` : '新增解析器配置'}
        open={modalVisible}
        onCancel={() => { setModalVisible(false); form.resetFields(); setEditing(null); }}
        onOk={handleSubmit}
        width={600}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="配置名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如: EAHI5-20K逆变器解析" />
          </Form.Item>
          <Form.Item name="device_type" label="设备类型" rules={[{ required: true, message: '请输入设备类型' }]}>
            <Select placeholder="选择设备类型">
              <Select.Option value="inverter_eahi_20k">逆变器 EAHI5-20K</Select.Option>
              <Select.Option value="pcs_100kw">PCS 100kW</Select.Option>
              <Select.Option value="charger_dc_60kw">直流充电桩 60kW</Select.Option>
              <Select.Option value="meter_three_phase">三相电表</Select.Option>
              <Select.Option value="bms_lithium">锂电池BMS</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="protocol" label="协议类型" rules={[{ required: true, message: '请选择协议' }]}>
            <Select placeholder="选择协议">
              <Select.Option value="modbus_rtu">Modbus RTU</Select.Option>
              <Select.Option value="modbus_tcp">Modbus TCP</Select.Option>
              <Select.Option value="mqtt">MQTT</Select.Option>
              <Select.Option value="rest">REST API</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="parser_schema" label="解析Schema">
            <Select placeholder="选择Schema" allowClear>
              <Select.Option value="modbus_inverter">Modbus 逆变器（300+字段）</Select.Option>
              <Select.Option value="modbus_pcs">Modbus PCS（200+字段）</Select.Option>
              <Select.Option value="mqtt_charger">MQTT 充电桩（150+字段）</Select.Option>
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

export default ParserConfigPage;