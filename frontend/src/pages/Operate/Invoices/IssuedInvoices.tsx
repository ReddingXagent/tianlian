/**
 * 天链 V3 — 已开发票列表页
 *
 * 卡 6d06831d (B1 下线旧 OpsInvoice): 数据源切换为 InvoiceRequest 新体系
 * (GET /ops/invoice-requests?status=issued, 契约 §5.4)。
 * 金额用后端预折算 amount_yuan (分→元)。
 *
 * 卡 f42bdf5a (Phase2-B2 红冲迁入): POST /ops/invoice-requests/{id}/void。
 * R1 方案b —— status 三态不变, 红冲打 voided 标记:
 * 已红冲行显示「已红冲」Tag + 隐藏红冲入口; 未红冲行可红冲 (理由必填)。
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Table, Tag, Button, Tooltip, Modal, Input, message, Space } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { opsInvoiceRequestAPI } from '../../../api/settlement';

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待开票' },
  issued: { color: 'green', text: '已开具' },
  rejected: { color: 'red', text: '已拒绝' },
};

const FILE_TYPE_TEXT: Record<string, string> = {
  pdf: 'PDF',
  ofd: 'OFD',
  image: '图片',
};

interface RequestItem {
  id: number;
  user_id: number | null;
  team_id: number | null;
  status: string;
  amount: number;          // 分 (契约 §6)
  amount_yuan?: number;    // 后端预折算元
  title_type: string;
  title_name: string;
  tax_number: string | null;
  order_ids: string[];
  invoice_file_name: string | null;
  invoice_file_type: string | null;
  issuer: number | null;
  issued_at: string | null;
  applied_at: string | null;
  // 红冲标记 (卡 f42bdf5a, R1 方案b: 未红冲恒 voided=false)
  voided?: boolean;
  void_reason?: string | null;
  voided_by?: number | null;
  voided_at?: string | null;
}

const IssuedInvoicesPage: React.FC = () => {
  const [data, setData] = useState<RequestItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [voidModal, setVoidModal] = useState<RequestItem | null>(null);
  const [voidReason, setVoidReason] = useState('');
  const [voiding, setVoiding] = useState(false);

  const loadData = useCallback(async (p = page) => {
    setLoading(true);
    try {
      const { data: res } = await opsInvoiceRequestAPI.list({
        status: 'issued', page: p, page_size: 20,
      });
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

  const closeVoid = () => {
    setVoidModal(null);
    setVoidReason('');
  };

  const handleVoid = async () => {
    if (!voidModal) return;
    if (!voidReason.trim()) {
      message.warning('请填写红冲原因');
      return;
    }
    setVoiding(true);
    try {
      await opsInvoiceRequestAPI.void(voidModal.id, { reason: voidReason.trim() });
      message.success('发票已红冲');
      closeVoid();
      loadData();
    } catch {
      message.error('红冲失败');
    } finally {
      setVoiding(false);
    }
  };

  const columns = [
    { title: '抬头', dataIndex: 'title_name', key: 'title_name', width: 180 },
    { title: '税号', dataIndex: 'tax_number', key: 'tax_number', width: 150, render: (v: string | null) => v || '-' },
    {
      title: '订单号', dataIndex: 'order_ids', key: 'order_ids', width: 170,
      render: (ids: string[]) => (
        <Tooltip title={ids?.join(', ')}>
          <span>{ids && ids.length ? ids[0] : '-'}{ids && ids.length > 1 ? ` 等${ids.length}单` : ''}</span>
        </Tooltip>
      ),
    },
    {
      title: '金额', key: 'amount', width: 100, align: 'right' as const,
      render: (_: unknown, r: RequestItem) => {
        const yuan = r.amount_yuan ?? (r.amount ? r.amount / 100 : 0);
        return `¥${yuan.toFixed(2)}`;
      },
    },
    {
      title: '发票文件', dataIndex: 'invoice_file_name', key: 'invoice_file_name', width: 180,
      render: (v: string | null, r: RequestItem) =>
        v ? `${v} (${FILE_TYPE_TEXT[r.invoice_file_type ?? ''] ?? r.invoice_file_type})` : '-',
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (v: string, r: RequestItem) => (
        <Space size={4}>
          <Tag color={STATUS_MAP[v]?.color || 'default'}>{STATUS_MAP[v]?.text || v}</Tag>
          {r.voided && <Tag color="volcano">已红冲</Tag>}
        </Space>
      ),
    },
    { title: '开具人', dataIndex: 'issuer', key: 'issuer', width: 80, render: (v: number | null) => v ?? '-' },
    {
      title: '开具时间', dataIndex: 'issued_at', key: 'issued_at', width: 150,
      render: (v: string | null) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作', key: 'action', width: 80,
      render: (_: unknown, r: RequestItem) => (
        r.voided ? <span style={{ color: '#999' }}>-</span> : (
          <Button size="small" type="link" danger onClick={() => setVoidModal(r)}>红冲</Button>
        )
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
        <Button icon={<ReloadOutlined />} onClick={() => loadData()}>刷新</Button>
      </div>
      <Table columns={columns} dataSource={data} rowKey="id" loading={loading} size="small"
        pagination={{ current: page, total, pageSize: 20, onChange: (p) => { setPage(p); loadData(p); } }}
      />

      <Modal
        title="红冲发票"
        open={!!voidModal}
        onOk={handleVoid}
        onCancel={closeVoid}
        confirmLoading={voiding}
        okText="确认红冲"
        okButtonProps={{ danger: true }}
      >
        {voidModal && (
          <p style={{ color: '#666' }}>
            抬头: <strong>{voidModal.title_name}</strong>　金额: ¥{(voidModal.amount_yuan ?? voidModal.amount / 100).toFixed(2)}
          </p>
        )}
        <Input.TextArea
          rows={3}
          placeholder="请填写红冲原因 (必填, 留档追溯)"
          value={voidReason}
          onChange={e => setVoidReason(e.target.value)}
        />
      </Modal>
    </div>
  );
};

export default IssuedInvoicesPage;
