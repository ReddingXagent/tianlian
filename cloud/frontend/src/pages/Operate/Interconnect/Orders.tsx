/**
 * 天链 V3 — 互联互通导流订单查询
 * 查看外部平台导流过来的充电订单, 支持来源平台筛选
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Table, Tag, Button, Space, Select, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { interconnectOrderAPI } from '../../../api/operateExternal';
import { fetchAllPages } from '../../../api/fetchAll';

interface InterconnectOrderItem {
  id: number;
  platform_id: number;
  platform_code: string;
  outer_order_id: string;
  outer_user_id?: string;
  station_id?: string;
  device_id?: string;
  charge_energy_kwh: number;
  total_amount: number;
  our_share: number;
  partner_share: number;
  status: string;
  synced_at?: string;
  created_at?: string;
}

const PLATFORM_OPTIONS = [
  { value: 'huawei', label: '华为云充电' },
  { value: 'sgcc', label: '国家电网' },
  { value: 'csg', label: '南方电网' },
  { value: 'teld', label: '特来电' },
  { value: 'other', label: '其他平台' },
];

const platformLabel = (code: string) => PLATFORM_OPTIONS.find(o => o.value === code)?.label || code || '-';

const ORDER_STATUS_MAP: Record<string, { color: string; text: string }> = {
  synced: { color: 'blue', text: '已同步' },
  settled: { color: 'green', text: '已结算' },
  conflict: { color: 'red', text: '冲突' },
};

const InterconnectOrders: React.FC = () => {
  const [data, setData] = useState<InterconnectOrderItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [platformCode, setPlatformCode] = useState<string | undefined>(undefined);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // 卡 fb183aaf: page_size 恰 100 上限会静默截断 → fetchAllPages 循环拉全量
      const items = await fetchAllPages<InterconnectOrderItem>(interconnectOrderAPI.list, {
        platform_code: platformCode,
      });
      setData(items);
    } catch {
      setData([]);
      message.error('订单列表加载失败');
    } finally {
      setLoading(false);
    }
  }, [platformCode]);

  useEffect(() => { loadData(); }, [loadData]);

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    {
      title: '来源平台', dataIndex: 'platform_code', key: 'platform_code', width: 120,
      render: (v: string) => <Tag color="blue">{platformLabel(v)}</Tag>,
    },
    { title: '外部订单号', dataIndex: 'outer_order_id', key: 'outer_order_id', width: 200 },
    {
      title: '充电量(kWh)', dataIndex: 'charge_energy_kwh', key: 'charge_energy_kwh', width: 120, align: 'right' as const,
      render: (v: number) => (v ?? 0).toFixed(2),
    },
    {
      title: '订单费用', dataIndex: 'total_amount', key: 'total_amount', width: 110, align: 'right' as const,
      render: (v: number) => <span style={{ fontWeight: 600 }}>¥ {(v ?? 0).toFixed(2)}</span>,
    },
    {
      title: '我方分成', dataIndex: 'our_share', key: 'our_share', width: 110, align: 'right' as const,
      render: (v: number) => <span style={{ color: '#34a853', fontWeight: 600 }}>¥ {(v ?? 0).toFixed(2)}</span>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string) => <Tag color={ORDER_STATUS_MAP[v]?.color || 'default'}>{ORDER_STATUS_MAP[v]?.text || v}</Tag>,
    },
    { title: '同步时间', dataIndex: 'synced_at', key: 'synced_at', width: 160, render: (v: string) => v || '-' },
  ];

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <span>来源平台：</span>
          <Select
            style={{ width: 180 }}
            allowClear
            placeholder="全部平台"
            value={platformCode}
            onChange={(v) => setPlatformCode(v)}
            options={PLATFORM_OPTIONS}
          />
        </Space>
        <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
      </div>
      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        scroll={{ x: 1000 }}
        pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
      />
    </>
  );
};

export default InterconnectOrders;
