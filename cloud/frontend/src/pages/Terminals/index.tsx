/**
 * 天链 V3 — 终端设备管理 (SPEC §2.4 物联网接入)
 * 终端设备(摄像头/传感器/门禁)的接入登记与状态管理
 *   - 列表(编号/类型/站点/IP/状态) + 按站点/类型/状态筛选 + 关键字搜索
 *   - 新增/编辑 Modal(含 RTSP 流地址 + 录制配置)
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm, Switch, InputNumber,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, SearchOutlined,
} from '@ant-design/icons';
import { terminalsAPI } from '../../api/admin';
import { fetchAllPages } from '../../api/fetchAll';

interface TerminalItem {
  id: number;
  terminal_code: string;
  terminal_type: string;
  station_name?: string | null;
  ip_address?: string | null;
  rtsp_url?: string | null;
  recording_config?: { enable?: boolean; quality?: string; retention_days?: number } | null;
  status: string;
  remark?: string | null;
  created_at?: string;
  updated_at?: string;
}

const TYPE_OPTIONS = [
  { value: 'camera', label: '摄像头' },
  { value: 'sensor', label: '传感器' },
  { value: 'access_control', label: '门禁' },
];
const STATUS_OPTIONS = [
  { value: 'online', label: '在线' },
  { value: 'offline', label: '离线' },
  { value: 'maintenance', label: '维护中' },
];
const QUALITY_OPTIONS = [
  { value: '720p', label: '720p' },
  { value: '1080p', label: '1080p' },
  { value: '4k', label: '4K' },
];

const typeLabel = (v: string) => TYPE_OPTIONS.find(o => o.value === v)?.label || v;
const typeColor: Record<string, string> = { camera: 'blue', sensor: 'cyan', access_control: 'purple' };
const statusColor: Record<string, string> = { online: 'green', offline: 'default', maintenance: 'orange' };
const statusLabel = (v: string) => STATUS_OPTIONS.find(o => o.value === v)?.label || v;

const TerminalsPage: React.FC = () => {
  const [data, setData] = useState<TerminalItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<TerminalItem | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [filters, setFilters] = useState<{ terminal_type?: string; station_name?: string; status?: string; keyword?: string }>({});
  const [form] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const items = await fetchAllPages<TerminalItem>((params) => terminalsAPI.list({
        ...filters,
        page: params.page as number,
        page_size: params.page_size as number,
      }));
      setData(items);
    } catch (err: any) {
      message.error('加载终端设备列表失败：' + (err?.response?.data?.detail || err?.message));
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { loadData(); }, [loadData]);

  const openCreate = () => {
    setEditingItem(null);
    form.resetFields();
    form.setFieldsValue({ terminal_type: 'camera', status: 'online', record_enable: false, record_quality: '1080p', record_retention: 30 });
    setModalOpen(true);
  };

  const openEdit = (record: TerminalItem) => {
    setEditingItem(record);
    form.setFieldsValue({
      terminal_code: record.terminal_code,
      terminal_type: record.terminal_type,
      station_name: record.station_name,
      ip_address: record.ip_address,
      rtsp_url: record.rtsp_url,
      status: record.status,
      remark: record.remark,
      record_enable: record.recording_config?.enable ?? false,
      record_quality: record.recording_config?.quality ?? '1080p',
      record_retention: record.recording_config?.retention_days ?? 30,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      const payload: Record<string, unknown> = {
        terminal_code: values.terminal_code,
        terminal_type: values.terminal_type,
        station_name: values.station_name,
        ip_address: values.ip_address,
        rtsp_url: values.rtsp_url,
        status: values.status,
        remark: values.remark,
      };
      if (values.terminal_type === 'camera' || values.record_enable) {
        payload.recording_config = {
          enable: !!values.record_enable,
          quality: values.record_quality || '1080p',
          retention_days: values.record_retention ?? 30,
        };
      }
      if (editingItem) {
        await terminalsAPI.update(editingItem.id, payload);
        message.success('终端设备已更新');
      } else {
        await terminalsAPI.create(payload);
        message.success('终端设备已创建');
      }
      setModalOpen(false);
      form.resetFields();
      setEditingItem(null);
      loadData();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await terminalsAPI.delete(id);
      message.success('已删除');
      loadData();
    } catch (err: any) {
      message.error('删除失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '终端编号', dataIndex: 'terminal_code', key: 'terminal_code', width: 140 },
    {
      title: '类型', dataIndex: 'terminal_type', key: 'terminal_type', width: 90,
      render: (v: string) => <Tag color={typeColor[v] || 'blue'}>{typeLabel(v)}</Tag>,
    },
    { title: '安装站点', dataIndex: 'station_name', key: 'station_name', width: 160, ellipsis: true },
    { title: 'IP地址', dataIndex: 'ip_address', key: 'ip_address', width: 130 },
    { title: '流地址', dataIndex: 'rtsp_url', key: 'rtsp_url', width: 200, ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string) => <Tag color={statusColor[v] || 'default'}>{statusLabel(v)}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 160, fixed: 'right' as const,
      render: (_: unknown, record: TerminalItem) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
          <Popconfirm title="确认删除该终端设备？" okText="确定" cancelText="取消" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <div className="page-container">
        <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }} wrap>
          <Space wrap>
            <Select
              allowClear placeholder="类型" style={{ width: 120 }}
              options={TYPE_OPTIONS}
              value={filters.terminal_type}
              onChange={(v) => setFilters(f => ({ ...f, terminal_type: v || undefined }))}
            />
            <Input
              allowClear placeholder="安装站点(精确)" style={{ width: 180 }}
              value={filters.station_name}
              onChange={(e) => setFilters(f => ({ ...f, station_name: e.target.value || undefined }))}
              onPressEnter={loadData}
            />
            <Select
              allowClear placeholder="状态" style={{ width: 120 }}
              options={STATUS_OPTIONS}
              value={filters.status}
              onChange={(v) => setFilters(f => ({ ...f, status: v || undefined }))}
            />
            <Input
              allowClear placeholder="编号关键字" style={{ width: 160 }}
              value={filters.keyword}
              onChange={(e) => setFilters(f => ({ ...f, keyword: e.target.value || undefined }))}
              onPressEnter={loadData}
            />
            <Button icon={<SearchOutlined />} type="primary" onClick={loadData}>查询</Button>
          </Space>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增终端</Button>
          </Space>
        </Space>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          scroll={{ x: 1200 }}
          pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
        />
      </div>
      <Modal
        title={editingItem ? '编辑终端设备' : '新增终端设备'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={submitting}
        onCancel={() => { setModalOpen(false); form.resetFields(); setEditingItem(null); }}
        width={620}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="terminal_code" label="终端编号" rules={[{ required: true, message: '请输入终端编号' }]}>
            <Input placeholder="如 CAM-A001" />
          </Form.Item>
          <Form.Item name="terminal_type" label="终端类型" rules={[{ required: true, message: '请选择终端类型' }]}>
            <Select options={TYPE_OPTIONS} placeholder="选择类型" />
          </Form.Item>
          <Form.Item name="station_name" label="安装站点">
            <Input placeholder="如 郑州东站充电站" />
          </Form.Item>
          <Form.Item name="ip_address" label="IP地址">
            <Input placeholder="如 192.168.1.100" />
          </Form.Item>
          <Form.Item name="rtsp_url" label="流地址(RTSP/RTMP)">
            <Input placeholder="如 rtsp://10.0.0.1:554/stream" />
          </Form.Item>
          <Form.Item name="record_enable" label="录制启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="record_quality" label="录制画质">
            <Select options={QUALITY_OPTIONS} />
          </Form.Item>
          <Form.Item name="record_retention" label="录制保留天数">
            <InputNumber style={{ width: '100%' }} min={1} step={1} placeholder="如 30" />
          </Form.Item>
          <Form.Item name="status" label="状态" rules={[{ required: true, message: '请选择状态' }]}>
            <Select options={STATUS_OPTIONS} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} placeholder="选填" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default TerminalsPage;
