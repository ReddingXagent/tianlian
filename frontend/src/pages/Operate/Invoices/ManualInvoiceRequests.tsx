/**
 * 天链 V3 — 手动开票申请 (卡 a09f8a21 契约 §5.4)
 *
 * C端用户对已支付订单提交开票申请 (InvoiceRequest, PENDING) → 运营在此:
 * - 上传发票文件 (PDF/OFD/jpg/png ≤10MB) → ISSUED, 云端推送通知
 * - 拒绝开票 (填理由) → REJECTED, 用户可重新申请
 *
 * 与 PendingInvoices (旧 OpsInvoice 审核流) 并列于「待审核」Tab。
 * 金额单位: 后端返回分 (契约 §6), 前端 /100 折算为元。
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Table, Tag, Button, Space, Modal, Input, Upload, message, Tooltip } from 'antd';
import type { UploadFile } from 'antd';
import { InboxOutlined, ReloadOutlined, CloseOutlined } from '@ant-design/icons';
import { opsInvoiceRequestAPI } from '../../../api/settlement';

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待开票' },
  issued: { color: 'green', text: '已开具' },
  rejected: { color: 'red', text: '已拒绝' },
};

const TITLE_TYPE_TEXT: Record<string, string> = {
  personal: '个人',
  company: '企业',
};

interface RequestItem {
  id: number;
  user_id: number | null;
  team_id: number | null;
  status: string;
  amount: number; // 分
  amount_yuan?: number;
  title_type: string;
  title_name: string;
  tax_number: string | null;
  email: string | null;
  order_ids: string[];
  remark: string | null;
  applied_at: string | null;
  reject_reason: string | null;
}

const ManualInvoiceRequestsPage: React.FC = () => {
  const [data, setData] = useState<RequestItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);

  const [uploadModal, setUploadModal] = useState<RequestItem | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  const [rejectModal, setRejectModal] = useState<RequestItem | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [rejecting, setRejecting] = useState(false);

  const loadData = useCallback(async (p = page) => {
    setLoading(true);
    try {
      const { data: res } = await opsInvoiceRequestAPI.list({ status: 'pending', page: p, page_size: 20 });
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

  const closeUpload = () => {
    setUploadModal(null);
    setUploadFile(null);
  };

  const handleUpload = async () => {
    if (!uploadModal) return;
    if (!uploadFile) {
      message.warning('请先选择发票文件');
      return;
    }
    setUploading(true);
    try {
      await opsInvoiceRequestAPI.upload(uploadModal.id, uploadFile);
      message.success('发票已上传, 状态已更新为已开具');
      closeUpload();
      loadData();
    } catch {
      message.error('上传失败');
    } finally {
      setUploading(false);
    }
  };

  const handleReject = async () => {
    if (!rejectModal) return;
    if (!rejectReason.trim()) {
      message.warning('请填写拒绝原因');
      return;
    }
    setRejecting(true);
    try {
      await opsInvoiceRequestAPI.reject(rejectModal.id, { reject_reason: rejectReason.trim() });
      message.success('已拒绝开票');
      setRejectModal(null);
      setRejectReason('');
      loadData();
    } catch {
      message.error('操作失败');
    } finally {
      setRejecting(false);
    }
  };

  const columns = [
    { title: '抬头', dataIndex: 'title_name', key: 'title_name', width: 200 },
    {
      title: '类型', dataIndex: 'title_type', key: 'title_type', width: 70,
      render: (v: string) => TITLE_TYPE_TEXT[v] || v,
    },
    { title: '税号', dataIndex: 'tax_number', key: 'tax_number', width: 160, render: (v: string | null) => v || '-' },
    {
      title: '订单号', dataIndex: 'order_ids', key: 'order_ids', width: 180,
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
        return <span style={{ fontWeight: 600 }}>¥{yuan.toFixed(2)}</span>;
      },
    },
    { title: '邮箱', dataIndex: 'email', key: 'email', width: 160, render: (v: string | null) => v || '-' },
    {
      title: '申请时间', dataIndex: 'applied_at', key: 'applied_at', width: 150,
      render: (v: string | null) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (v: string) => <Tag color={STATUS_MAP[v]?.color || 'default'}>{STATUS_MAP[v]?.text || v}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, r: RequestItem) => (
        <Space size="small">
          <Button size="small" type="link" onClick={() => setUploadModal(r)}>上传发票</Button>
          <Button size="small" type="link" danger icon={<CloseOutlined />} onClick={() => setRejectModal(r)}>拒绝</Button>
        </Space>
      ),
    },
  ];

  const uploadProps = {
    accept: '.pdf,.ofd,.jpg,.jpeg,.png',
    maxCount: 1,
    fileList: [] as UploadFile[],
    beforeUpload: (file: File) => {
      const isValidType = /\.(pdf|ofd|jpg|jpeg|png)$/i.test(file.name);
      if (!isValidType) {
        message.error('仅支持 PDF/OFD/jpg/png 格式');
        return Upload.LIST_IGNORE;
      }
      const isUnder10M = file.size / 1024 / 1024 <= 10;
      if (!isUnder10M) {
        message.error('文件超过 10MB 上限');
        return Upload.LIST_IGNORE;
      }
      setUploadFile(file);
      return false; // 阻止自动上传, 由「确认上传」按钮手动调 API
    },
    onRemove: () => setUploadFile(null),
  };

  return (
    <div>
      <div style={{ marginBottom: 8, marginTop: 4 }}>
        <strong>手动开票申请</strong>
        <span style={{ color: '#999', marginLeft: 8 }}>C端用户提交, 上传发票文件后状态变「已开具」并通知用户</span>
        <Button size="small" icon={<ReloadOutlined />} style={{ marginLeft: 12 }} onClick={() => loadData()}>刷新</Button>
      </div>
      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => { setPage(p); loadData(p); },
        }}
      />

      <Modal
        title="上传发票文件"
        open={!!uploadModal}
        onOk={handleUpload}
        onCancel={closeUpload}
        confirmLoading={uploading}
        okText="确认上传"
      >
        {uploadModal && (
          <p style={{ color: '#666' }}>
            抬头: <strong>{uploadModal.title_name}</strong>　金额: ¥{(uploadModal.amount_yuan ?? uploadModal.amount / 100).toFixed(2)}
          </p>
        )}
        <Upload.Dragger {...uploadProps}>
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
          <p className="ant-upload-hint">支持 PDF / OFD / jpg / png, 单文件 ≤10MB</p>
        </Upload.Dragger>
      </Modal>

      <Modal
        title="拒绝开票"
        open={!!rejectModal}
        onOk={handleReject}
        onCancel={() => { setRejectModal(null); setRejectReason(''); }}
        confirmLoading={rejecting}
        okText="确认拒绝"
      >
        <Input.TextArea
          rows={3}
          placeholder="请填写拒绝原因 (用户可见, 拒绝后用户可重新申请)"
          value={rejectReason}
          onChange={e => setRejectReason(e.target.value)}
        />
      </Modal>
    </div>
  );
};

export default ManualInvoiceRequestsPage;
