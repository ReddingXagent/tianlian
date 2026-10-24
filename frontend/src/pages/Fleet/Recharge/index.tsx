/**
 * 天链 V3 - 车队充值页面
 *
 * 车队用户发起充值申请 → 上传付款凭证 → 等待运营商审核
 */
import React, { useState, useCallback, useEffect } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, InputNumber, Upload, message,
  Space, Row, Col, Statistic, Popconfirm,
} from 'antd';
import {
  DollarOutlined, UploadOutlined, ReloadOutlined,
  CheckCircleOutlined, ClockCircleOutlined, CloseCircleOutlined,
} from '@ant-design/icons';
import type { UploadFile } from 'antd';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';
import VoucherView from '../../../components/VoucherView';
import { useIsMobile } from '../../../hooks/useIsMobile';

const STATUS_TAGS: Record<string, { color: string; text: string; icon: React.ReactNode }> = {
  pending: { color: 'orange', text: '待审核', icon: <ClockCircleOutlined /> },
  approved: { color: 'green', text: '已通过', icon: <CheckCircleOutlined /> },
  rejected: { color: 'red', text: '已驳回', icon: <CloseCircleOutlined /> },
};

const FleetRechargePage: React.FC = () => {
  const isMobile = useIsMobile();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [records, setRecords] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [page_size, setPageSize] = useState(10);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [enterpriseId, setEnterpriseId] = useState<number | undefined>(undefined);
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { page, page_size };
      if (statusFilter) params.status = statusFilter;
      if (enterpriseId) params.enterprise_id = enterpriseId;
      const { data } = await api.get('/fleet/recharge', { params });
      const items = data?.data?.items || data?.data || data?.items || [];
      setRecords(Array.isArray(items) ? items : []);
      setTotal(data?.data?.total || data?.total || 0);
    } catch (err: any) {
      message.error('加载充值记录失败：' + (err?.response?.data?.detail || err?.message));
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, [page, page_size, statusFilter, enterpriseId]);

  useEffect(() => { loadRecords(); }, [loadRecords]);

  // 获取当前用户的企业
  useEffect(() => {
    api.get('/fleet/enterprises').then(({ data }) => {
      const items = Array.isArray(data) ? data : (data?.data?.items || data?.items || []);
      if (items.length > 0) setEnterpriseId(items[0].id);
    }).catch((err: any) => {
      message.error('加载企业列表失败：' + (err?.response?.data?.detail || err?.message));
    });
  }, []);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (fileList.length === 0) {
        message.warning('请上传付款凭证');
        return;
      }
      setSubmitting(true);
      const file = fileList[0].originFileObj || fileList[0] as any;
      const formData = new FormData();
      formData.append('enterprise_id', values.enterprise_id || enterpriseId || '');
      formData.append('amount', values.amount.toString());
      formData.append('file', file as File);

      await api.post('/fleet/recharge', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      message.success('充值申请已提交，等待审核');
      form.resetFields();
      setFileList([]);
      loadRecords();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('提交失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setSubmitting(false);
    }
  };

  const stats = {
    total: records.length,
    pending: records.filter(r => r.status === 'pending').length,
    approved: records.filter(r => r.status === 'approved').length,
    totalAmount: records.filter(r => r.status === 'approved').reduce((s, r) => s + (r.amount || 0), 0),
  };

  const columns = [
    {
      title: '企业', dataIndex: 'enterprise_name', key: 'enterprise_name', width: 140, ellipsis: true,
    },
    {
      title: '金额(元)', dataIndex: 'amount', key: 'amount', width: 100, align: 'right' as const,
      render: (v: number) => <span style={{ fontWeight: 600, color: '#1890ff' }}>¥ {v?.toFixed(2)}</span>,
    },
    {
      title: '凭证', dataIndex: 'voucher_url', key: 'voucher_url', width: 80,
      // 凭证改走鉴权端点 (卡 554bb70b), 不再用 /uploads 裸链
      render: (_: string, record: any) => <VoucherView record={record} />,
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
  ];

  return (
    <PageWrapper loading={loading && records.length === 0} skeletonType="table" skeletonCount={4} hasData={records.length > 0}>
      <div className="page-container">
        {/* 统计卡片 */}
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}><Card><Statistic title="总申请数" value={stats.total} prefix={<DollarOutlined />} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="待审核" value={stats.pending} valueStyle={{ color: '#fa8c16' }} prefix={<ClockCircleOutlined />} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="已通过" value={stats.approved} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="已入账总额" value={stats.totalAmount} precision={2} prefix="¥" valueStyle={{ color: '#1890ff' }} /></Card></Col>
        </Row>

        {/* 充值表单 */}
        <Card title="发起充值" style={{ marginBottom: 16 }}>
          <Form form={form} layout="inline" onFinish={handleSubmit}>
            <Form.Item name="amount" label="充值金额" rules={[{ required: true, message: '请输入金额' }]}>
              <InputNumber
                placeholder="请输入金额"
                min={0.01}
                step={100}
                precision={2}
                formatter={value => `¥ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                style={{ width: 200 }}
              />
            </Form.Item>
            <Form.Item label="付款凭证" required>
              <Upload
                fileList={fileList}
                beforeUpload={() => false}
                onChange={({ fileList: fl }) => setFileList(fl.slice(-1))}
                accept=".jpg,.jpeg,.png,.pdf,.webp"
                maxCount={1}
              >
                <Button icon={<UploadOutlined />}>选择文件</Button>
              </Upload>
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={submitting}>
                提交充值申请
              </Button>
            </Form.Item>
          </Form>
        </Card>

        {/* 记录列表 */}
        <Card
          title="充值记录"
          extra={
            <Space>
              <Button
                size="small"
                type={statusFilter === 'pending' ? 'primary' : 'default'}
                onClick={() => { setStatusFilter(statusFilter === 'pending' ? undefined : 'pending'); setPage(1); }}
              >待审核</Button>
              <Button
                size="small"
                type={statusFilter === 'approved' ? 'primary' : 'default'}
                onClick={() => { setStatusFilter(statusFilter === 'approved' ? undefined : 'approved'); setPage(1); }}
              >已通过</Button>
              <Button icon={<ReloadOutlined />} onClick={loadRecords}>刷新</Button>
            </Space>
          }
        >
          <Table
            columns={columns}
            dataSource={records}
            rowKey="id"
            loading={loading}
            scroll={{ x: 730 }}
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
      </div>
    </PageWrapper>
  );
};

export default FleetRechargePage;
