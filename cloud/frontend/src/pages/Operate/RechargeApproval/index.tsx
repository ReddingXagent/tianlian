/**
 * 天链 V3 - 运营商充值审核页面
 *
 * 运营商/admin 查看待审核充值申请 → 通过/驳回
 */
import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Table, Tag, Button, Modal, Input, message, Space,
  Tabs,
} from 'antd';
import {
  CheckCircleOutlined, CloseCircleOutlined, ReloadOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';
import VoucherView from '../../../components/VoucherView';

const STATUS_TAGS: Record<string, { color: string; text: string; icon: React.ReactNode }> = {
  pending: { color: 'orange', text: '待审核', icon: <ClockCircleOutlined /> },
  approved: { color: 'green', text: '已通过', icon: <CheckCircleOutlined /> },
  rejected: { color: 'red', text: '已驳回', icon: <CloseCircleOutlined /> },
};

const RechargeApprovalPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [records, setRecords] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [page_size, setPageSize] = useState(10);
  const [activeTab, setActiveTab] = useState('pending');
  const [rejectModal, setRejectModal] = useState<{ open: boolean; id?: number }>({ open: false });
  const [rejectRemark, setRejectRemark] = useState('');

  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { page, page_size };
      if (activeTab !== 'all') params.status = activeTab;
      const { data } = await api.get('/fleet/recharge', { params });
      const items = data?.data?.items || data?.data || data?.items || [];
      setRecords(Array.isArray(items) ? items : []);
      setTotal(data?.data?.total || data?.total || 0);
    } catch (err: any) {
      message.error('加载充值申请失败：' + (err?.response?.data?.detail || err?.message));
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, [page, page_size, activeTab]);

  useEffect(() => { loadRecords(); }, [loadRecords]);

  const handleApprove = async (id: number) => {
    try {
      await api.post(`/fleet/recharge/${id}/approve`);
      message.success('审核通过，余额已入账');
      loadRecords();
    } catch (err: any) {
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleReject = async () => {
    if (!rejectModal.id) return;
    if (!rejectRemark.trim()) {
      message.warning('请输入驳回理由');
      return;
    }
    try {
      await api.post(`/fleet/recharge/${rejectModal.id}/reject`, { remark: rejectRemark });
      message.success('已驳回');
      setRejectModal({ open: false });
      setRejectRemark('');
      loadRecords();
    } catch (err: any) {
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const columns = [
    {
      title: '企业', dataIndex: 'enterprise_name', key: 'enterprise_name', width: 140, ellipsis: true,
    },
    {
      title: '金额(元)', dataIndex: 'amount', key: 'amount', width: 110, align: 'right' as const,
      render: (v: number) => <span style={{ fontWeight: 600, color: '#1890ff' }}>¥ {v?.toFixed(2)}</span>,
    },
    {
      title: '凭证', dataIndex: 'voucher_url', key: 'voucher_url', width: 80,
      // 凭证改走鉴权端点 (卡 554bb70b), 不再用 /uploads 裸链
      render: (_: string, record: any) => <VoucherView record={record} thumbnail />,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (s: string) => {
        const cfg = STATUS_TAGS[s] || { color: 'default', text: s, icon: null };
        return <Tag color={cfg.color} icon={cfg.icon}>{cfg.text}</Tag>;
      },
    },
    {
      title: '审核备注', dataIndex: 'remark', key: 'remark', width: 160, ellipsis: true,
      render: (v: string) => v || '-',
    },
    {
      title: '申请时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作', key: 'action', width: 140, fixed: 'right' as const,
      render: (_: unknown, record: any) =>
        record.status === 'pending' ? (
          <Space>
            <Button type="primary" size="small" icon={<CheckCircleOutlined />}
              onClick={() => handleApprove(record.id)}
            >通过</Button>
            <Button danger size="small" icon={<CloseCircleOutlined />}
              onClick={() => setRejectModal({ open: true, id: record.id })}
            >驳回</Button>
          </Space>
        ) : '-',
    },
  ];

  return (
    <PageWrapper loading={loading && records.length === 0} skeletonType="table" skeletonCount={4} hasData={records.length > 0}>
      <div className="page-container">
        <Card
          extra={
            <Button icon={<ReloadOutlined />} onClick={loadRecords}>刷新</Button>
          }
        >
          <Tabs
            activeKey={activeTab}
            onChange={(key) => { setActiveTab(key); setPage(1); }}
            items={[
              { key: 'pending', label: '待审核' },
              { key: 'approved', label: '已通过' },
              { key: 'rejected', label: '已驳回' },
              { key: 'all', label: '全部' },
            ]}
          />
          <Table
            columns={columns}
            dataSource={records}
            rowKey="id"
            loading={loading}
            scroll={{ x: 880 }}
            pagination={{
              current: page,
              pageSize: page_size,
              total,
              showSizeChanger: true,
              onChange: (p, ps) => { setPage(p); setPageSize(ps); },
              showTotal: (t: number) => `共 ${t} 条`,
            }}
          />
        </Card>

        {/* 驳回 Modal */}
        <Modal
          title="驳回充值申请"
          open={rejectModal.open}
          onOk={handleReject}
          onCancel={() => { setRejectModal({ open: false }); setRejectRemark(''); }}
          okText="确认驳回"
          okButtonProps={{ danger: true }}
        >
          <Input.TextArea
            rows={3}
            placeholder="请输入驳回理由"
            value={rejectRemark}
            onChange={e => setRejectRemark(e.target.value)}
            maxLength={500}
            showCount
          />
        </Modal>
      </div>
    </PageWrapper>
  );
};

export default RechargeApprovalPage;
