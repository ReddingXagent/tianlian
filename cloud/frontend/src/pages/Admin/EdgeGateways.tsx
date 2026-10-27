/**
 * 天链 V3 — 管理后台: 边缘网关 SN 平台台账 (任务卡 e940c9f4)
 * 平台提供方同时提供边缘网关硬件, 其 SN 在平台管理界面操作管理。
 *   - SN 列表 (编号/批次/状态Tag/绑定场站/固件/上线时间)
 *   - 状态筛选 + 批次筛选 + SN 关键字搜索 + 分页
 *   - 批量生成 SN (指定数量/区域/批次号)
 *   - 绑定场站弹窗 (校验站点存在) / 解绑 / 出库 / 上线 / 退役
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  InputNumber, Tooltip,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, SearchOutlined, LinkOutlined,
  DisconnectOutlined, ExportOutlined, ThunderboltOutlined, StopOutlined,
} from '@ant-design/icons';
import { edgeGatewayAPI } from '../../api/admin';
import { stationAPI } from '../../api/index';

interface EdgeGatewayItem {
  id: number;
  sn: string;
  batch?: string | null;
  status: string;
  station_id?: number | null;
  firmware_version?: string | null;
  last_online_at?: string | null;
  created_at?: string;
}

interface StationOption {
  id: number;
  name?: string;
  code?: string;
}

const STATUS_OPTIONS = [
  { value: 'inventory', label: '入库' },
  { value: 'shipped', label: '已发货' },
  { value: 'bound', label: '已绑定' },
  { value: 'online', label: '在线' },
  { value: 'decommissioned', label: '已退役' },
];

const statusColor: Record<string, string> = {
  inventory: 'default',
  shipped: 'blue',
  bound: 'gold',
  online: 'green',
  decommissioned: 'red',
};
const statusLabel = (v: string) => STATUS_OPTIONS.find(o => o.value === v)?.label || v;

const REGION_OPTIONS = [
  { value: 'HN', label: '河南(HN)' },
  { value: 'GD', label: '广东(GD)' },
  { value: 'JS', label: '江苏(JS)' },
  { value: 'BJ', label: '北京(BJ)' },
  { value: 'SH', label: '上海(SH)' },
];

const EdgeGatewaysPage: React.FC = () => {
  const [data, setData] = useState<EdgeGatewayItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [filters, setFilters] = useState<{ status?: string; batch?: string; keyword?: string }>({});

  // 批量生成弹窗
  const [genOpen, setGenOpen] = useState(false);
  const [genSubmitting, setGenSubmitting] = useState(false);
  const [genForm] = Form.useForm();

  // 绑定弹窗
  const [bindOpen, setBindOpen] = useState(false);
  const [bindSn, setBindSn] = useState<string>('');
  const [bindSubmitting, setBindSubmitting] = useState(false);
  const [stations, setStations] = useState<StationOption[]>([]);
  const [stationsLoading, setStationsLoading] = useState(false);
  const [bindForm] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const { data: res } = await edgeGatewayAPI.list({ ...filters, page, page_size: pageSize });
      const payload = (res as any)?.data ?? res;
      setData(payload?.items ?? []);
      setTotal(payload?.total ?? 0);
    } catch {
      setData([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [filters, page, pageSize]);

  useEffect(() => { loadData(); }, [loadData]);

  const openGenerate = () => {
    genForm.resetFields();
    genForm.setFieldsValue({ count: 10, region: 'HN' });
    setGenOpen(true);
  };

  const handleGenerate = async () => {
    try {
      const values = await genForm.validateFields();
      setGenSubmitting(true);
      const { data: res } = await edgeGatewayAPI.generate({
        count: values.count,
        region: values.region || 'HN',
        batch: values.batch || undefined,
      });
      const sns = (res as any)?.data?.sn_list ?? (res as any)?.sn_list ?? [];
      message.success(`已生成 ${sns.length} 个 SN`);
      setGenOpen(false);
      setPage(1);
      loadData();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('生成失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setGenSubmitting(false);
    }
  };

  const loadStations = useCallback(async () => {
    setStationsLoading(true);
    try {
      const { data: res } = await stationAPI.list();
      const list = (res as any)?.data ?? res;
      const arr: StationOption[] = Array.isArray(list) ? list : (list?.items ?? []);
      setStations(arr.map((s: any) => ({ id: s.id, name: s.name, code: s.code })));
    } catch {
      setStations([]);
    } finally {
      setStationsLoading(false);
    }
  }, []);

  const openBind = (sn: string) => {
    setBindSn(sn);
    bindForm.resetFields();
    setBindOpen(true);
    if (stations.length === 0) loadStations();
  };

  const handleBind = async () => {
    try {
      const values = await bindForm.validateFields();
      setBindSubmitting(true);
      await edgeGatewayAPI.bind(bindSn, values.station_id);
      message.success('已绑定场站');
      setBindOpen(false);
      loadData();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('绑定失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setBindSubmitting(false);
    }
  };

  const transition = async (
    sn: string, fn: (s: string) => Promise<unknown>, okMsg: string, errMsg: string,
  ) => {
    try {
      await fn(sn);
      message.success(okMsg);
      loadData();
    } catch (err: any) {
      message.error(errMsg + '：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: 'SN', dataIndex: 'sn', key: 'sn', width: 130 },
    { title: '批次', dataIndex: 'batch', key: 'batch', width: 120, render: (v: string) => v || '-' },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string) => <Tag color={statusColor[v] || 'default'}>{statusLabel(v)}</Tag>,
    },
    { title: '绑定场站', dataIndex: 'station_id', key: 'station_id', width: 100, render: (v: number) => v ?? '-' },
    { title: '固件版本', dataIndex: 'firmware_version', key: 'firmware_version', width: 110, render: (v: string) => v || '-' },
    {
      title: '上线时间', dataIndex: 'last_online_at', key: 'last_online_at', width: 170,
      render: (v: string) => v || '-',
    },
    {
      title: '操作', key: 'action', width: 280, fixed: 'right' as const,
      render: (_: unknown, record: EdgeGatewayItem) => {
        const decommissioned = record.status === 'decommissioned';
        return (
          <Space size={0} wrap>
            <Tooltip title="出库/发货">
              <Button size="small" icon={<ExportOutlined />} disabled={decommissioned}
                onClick={() => transition(record.sn, edgeGatewayAPI.ship, '已出库', '出库失败')}>出库</Button>
            </Tooltip>
            <Tooltip title="绑定场站">
              <Button size="small" icon={<LinkOutlined />} disabled={decommissioned}
                onClick={() => openBind(record.sn)}>绑定</Button>
            </Tooltip>
            <Tooltip title="解绑">
              <Button size="small" icon={<DisconnectOutlined />} disabled={decommissioned || !record.station_id}
                onClick={() => transition(record.sn, edgeGatewayAPI.unbind, '已解绑', '解绑失败')}>解绑</Button>
            </Tooltip>
            <Tooltip title="上线(接入钩子)">
              <Button size="small" icon={<ThunderboltOutlined />} disabled={decommissioned}
                onClick={() => transition(record.sn, (s) => edgeGatewayAPI.online(s), '已上线', '上线失败')}>上线</Button>
            </Tooltip>
            <Tooltip title="退役">
              <Button size="small" danger icon={<StopOutlined />} disabled={decommissioned}
                onClick={() => transition(record.sn, edgeGatewayAPI.decommission, '已退役', '退役失败')}>退役</Button>
            </Tooltip>
          </Space>
        );
      },
    },
  ];

  return (
    <>
      <div className="page-container">
        <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }} wrap>
          <Space wrap>
            <Select
              allowClear placeholder="状态" style={{ width: 120 }}
              options={STATUS_OPTIONS}
              value={filters.status}
              onChange={(v) => { setFilters(f => ({ ...f, status: v || undefined })); setPage(1); }}
            />
            <Input
              allowClear placeholder="批次号" style={{ width: 150 }}
              value={filters.batch}
              onChange={(e) => setFilters(f => ({ ...f, batch: e.target.value || undefined }))}
              onPressEnter={() => { setPage(1); loadData(); }}
            />
            <Input
              allowClear placeholder="SN 关键字" style={{ width: 160 }}
              value={filters.keyword}
              onChange={(e) => setFilters(f => ({ ...f, keyword: e.target.value || undefined }))}
              onPressEnter={() => { setPage(1); loadData(); }}
            />
            <Button icon={<SearchOutlined />} type="primary" onClick={() => { setPage(1); loadData(); }}>查询</Button>
          </Space>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openGenerate}>批量生成SN</Button>
          </Space>
        </Space>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          scroll={{ x: 1300 }}
          pagination={{
            current: page, pageSize, total,
            showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`,
            onChange: (p, ps) => { setPage(p); setPageSize(ps); },
          }}
        />
      </div>

      {/* 批量生成 SN 弹窗 */}
      <Modal
        title="批量生成边缘网关 SN"
        open={genOpen}
        onOk={handleGenerate}
        confirmLoading={genSubmitting}
        onCancel={() => { setGenOpen(false); genForm.resetFields(); }}
        width={480}
        destroyOnHidden
      >
        <Form form={genForm} layout="vertical">
          <Form.Item name="count" label="生成数量" rules={[{ required: true, message: '请输入数量(1-1000)' }]}>
            <InputNumber style={{ width: '100%' }} min={1} max={1000} step={1} placeholder="如 50" />
          </Form.Item>
          <Form.Item name="region" label="区域码" rules={[{ required: true, message: '请选择区域码' }]}>
            <Select options={REGION_OPTIONS} placeholder="选择区域" />
          </Form.Item>
          <Form.Item name="batch" label="批次号(选填)">
            <Input placeholder="如 B202608-01, 便于按批追溯" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 绑定场站弹窗 */}
      <Modal
        title={`绑定场站 — ${bindSn}`}
        open={bindOpen}
        onOk={handleBind}
        confirmLoading={bindSubmitting}
        onCancel={() => { setBindOpen(false); bindForm.resetFields(); }}
        width={460}
        destroyOnHidden
      >
        <Form form={bindForm} layout="vertical">
          <Form.Item name="station_id" label="选择场站" rules={[{ required: true, message: '请选择场站' }]}>
            <Select
              loading={stationsLoading}
              placeholder="选择要绑定的场站"
              showSearch
              optionFilterProp="label"
              options={stations.map(s => ({ value: s.id, label: `${s.name || '(未命名)'} (#${s.id})` }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default EdgeGatewaysPage;
