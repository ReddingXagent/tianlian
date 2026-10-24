/**
 * 天链 V3 — 企业结算页
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Table, Tag, Button, Space } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { enterpriseSettlementAPI } from '../../../api/settlement';

const EnterpriseSettlementPage: React.FC = () => {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);

  const loadData = useCallback(async (p = page) => {
    setLoading(true);
    try {
      const { data: res } = await enterpriseSettlementAPI.list({ page: p, page_size: 20 });
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

  const columns = [
    { title: '账单号', dataIndex: 'bill_no', key: 'bill_no', width: 140 },
    { title: '企业ID', dataIndex: 'enterprise_id', key: 'enterprise_id', width: 80 },
    { title: '账期', dataIndex: 'bill_period', key: 'bill_period', width: 90 },
    { title: '订单数', dataIndex: 'total_orders', key: 'total_orders', width: 70, align: 'right' as const },
    { title: '应付总额', dataIndex: 'total_amount', key: 'total_amount', width: 110, align: 'right' as const, render: (v: number) => `¥${(v ?? 0).toFixed(2)}` },
    { title: '已付', dataIndex: 'paid_amount', key: 'paid_amount', width: 100, align: 'right' as const, render: (v: number) => <span style={{ color: '#34a853' }}>¥{(v ?? 0).toFixed(2)}</span> },
    { title: '待结', dataIndex: 'balance_amount', key: 'balance_amount', width: 100, align: 'right' as const, render: (v: number) => v ? <span style={{ color: '#f5222d' }}>¥{v.toFixed(2)}</span> : '-' },
    { title: '状态', dataIndex: 'status', key: 'status', width: 80, render: (v: string) => {
      const m: Record<string, { color: string; text: string }> = { pending: { color: 'orange', text: '待确认' }, confirmed: { color: 'blue', text: '已确认' }, paid: { color: 'green', text: '已付款' } };
      return <Tag color={m[v]?.color || 'default'}>{m[v]?.text || v}</Tag>;
    } },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadData()}>刷新</Button>
        </Space>
      </div>
      <Table columns={columns} dataSource={data} rowKey="id" loading={loading} size="small"
        pagination={{ current: page, total, pageSize: 20, onChange: (p) => { setPage(p); loadData(p); } }}
      />
    </div>
  );
};

export default EnterpriseSettlementPage;
