/**
 * Runbook审批管理页面
 */
import React, { useState, useEffect } from 'react';
import {
  Card, Table, Button, Modal, Form, Input, Tag, Space, message,
  Tabs, Row, Col, Statistic, Descriptions, Popconfirm, Alert, Badge
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  AuditOutlined, CheckOutlined, CloseOutlined, ClockCircleOutlined,
  HistoryOutlined, WarningOutlined, ThunderboltOutlined
} from '@ant-design/icons';
import api from '../../api';

const { TextArea } = Input;

interface ApprovalRecord {
  id: number;
  runbook_id: string;
  alarm_id: number;
  step_index: number;
  step_description: string;
  action_type: string;
  command_preview: string;
  risk_level: string;
  rollback_preview?: string;
  required_level: string;
  status: string;
  approver_id?: number;
  approver_name?: string;
  reject_reason?: string;
  expires_at?: string;
  created_at: string;
  approved_at?: string;
}

const RunbookApprovalPage: React.FC = () => {
  const [pending, setPending] = useState<ApprovalRecord[]>([]);
  const [history, setHistory] = useState<ApprovalRecord[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [approveModalVisible, setApproveModalVisible] = useState(false);
  const [rejectModalVisible, setRejectModalVisible] = useState(false);
  const [selectedApproval, setSelectedApproval] = useState<ApprovalRecord | null>(null);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [approveForm] = Form.useForm();
  const [rejectForm] = Form.useForm();

  const fetchPending = async () => {
    setLoading(true);
    try {
      const res = await api.get('/runbook/approvals/pending');
      const data = res.data as any;
      setPending(data.items || data || []);
    } catch (error) {
      message.error('获取待审批列表失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchHistory = async () => {
    try {
      const res = await api.get('/runbook/approvals/history');
      const data = res.data as any;
      setHistory(data.items || data || []);
    } catch (error) {
      // ignore
    }
  };

  const fetchStats = async () => {
    try {
      const res = await api.get('/runbook/approvals/stats');
      setStats(res.data);
    } catch (error) {
      // ignore
    }
  };

  useEffect(() => {
    fetchPending();
    fetchHistory();
    fetchStats();
  }, []);

  const handleApprove = async (values: any) => {
    if (!selectedApproval) return;
    try {
      await api.post(`/runbook/approvals/${selectedApproval.id}/approve`, { comment: values.comment });
      message.success('审批通过');
      setApproveModalVisible(false);
      approveForm.resetFields();
      fetchPending();
      fetchHistory();
      fetchStats();
    } catch (error: any) {
      message.error(error.response?.data?.message || '审批失败');
    }
  };

  const handleReject = async (values: any) => {
    if (!selectedApproval) return;
    try {
      await api.post(`/runbook/approvals/${selectedApproval.id}/reject`, { reason: values.reason });
      message.success('已拒绝');
      setRejectModalVisible(false);
      rejectForm.resetFields();
      fetchPending();
      fetchHistory();
      fetchStats();
    } catch (error: any) {
      message.error(error.response?.data?.message || '拒绝失败');
    }
  };

  const handleExpireCheck = async () => {
    try {
      await api.post('/runbook/approvals/expire-check');
      message.success('超时检查完成');
      fetchPending();
      fetchHistory();
    } catch (error) {
      message.error('检查失败');
    }
  };

  const getRiskTag = (risk: string) => {
    const map: Record<string, { color: string; text: string }> = {
      low: { color: 'green', text: '低风险' },
      medium: { color: 'orange', text: '中风险' },
      high: { color: 'red', text: '高风险' },
      critical: { color: 'magenta', text: '极高风险' },
    };
    return map[risk] || { color: 'default', text: risk };
  };

  const getStatusTag = (status: string) => {
    const map: Record<string, { color: string; text: string }> = {
      pending: { color: 'blue', text: '待审批' },
      approved: { color: 'green', text: '已通过' },
      rejected: { color: 'red', text: '已拒绝' },
      expired: { color: 'default', text: '已超时' },
    };
    return map[status] || { color: 'default', text: status };
  };

  const isExpired = (record: ApprovalRecord) => {
    if (!record.expires_at) return false;
    return new Date(record.expires_at) < new Date();
  };

  const pendingColumns: ColumnsType<ApprovalRecord> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: 'Runbook', dataIndex: 'runbook_id', width: 120 },
    { title: '告警ID', dataIndex: 'alarm_id', width: 80 },
    { title: '步骤', dataIndex: 'step_index', width: 60 },
    { title: '步骤描述', dataIndex: 'step_description', width: 200 },
    { title: '动作类型', dataIndex: 'action_type', width: 100, render: (v: string) => <Tag>{v}</Tag> },
    { title: '风险等级', dataIndex: 'risk_level', width: 100, render: (v: string) => {
      const t = getRiskTag(v);
      return <Tag color={t.color}>{t.text}</Tag>;
    }},
    { title: '所需级别', dataIndex: 'required_level', width: 100 },
    { title: '过期时间', dataIndex: 'expires_at', width: 160, render: (v: string, r: ApprovalRecord) => (
      isExpired(r) ? <Tag color="red">已过期</Tag> : v?.slice(0, 19)
    )},
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: (v: string) => v?.slice(0, 19) },
    { title: '操作', width: 180, fixed: 'right', render: (_: any, r: ApprovalRecord) => (
      <Space size="small">
        <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => { setSelectedApproval(r); setApproveModalVisible(true); }} disabled={isExpired(r)}>
          通过
        </Button>
        <Button size="small" danger icon={<CloseOutlined />} onClick={() => { setSelectedApproval(r); setRejectModalVisible(true); }} disabled={isExpired(r)}>
          拒绝
        </Button>
        <Button size="small" onClick={() => { setSelectedApproval(r); setDetailModalVisible(true); }}>详情</Button>
      </Space>
    )},
  ];

  const historyColumns: ColumnsType<ApprovalRecord> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: 'Runbook', dataIndex: 'runbook_id', width: 120 },
    { title: '告警ID', dataIndex: 'alarm_id', width: 80 },
    { title: '步骤描述', dataIndex: 'step_description', width: 200 },
    { title: '风险等级', dataIndex: 'risk_level', width: 100, render: (v: string) => {
      const t = getRiskTag(v);
      return <Tag color={t.color}>{t.text}</Tag>;
    }},
    { title: '状态', dataIndex: 'status', width: 100, render: (v: string) => {
      const t = getStatusTag(v);
      return <Tag color={t.color}>{t.text}</Tag>;
    }},
    { title: '审批人', dataIndex: 'approver_name', width: 120 },
    { title: '拒绝原因', dataIndex: 'reject_reason', width: 200 },
    { title: '审批时间', dataIndex: 'approved_at', width: 160, render: (v: string) => v?.slice(0, 19) || '-' },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: (v: string) => v?.slice(0, 19) },
  ];

  return (
    <Card title={<><AuditOutlined /> Runbook审批管理</>} extra={
      <Space>
        <Button icon={<ClockCircleOutlined />} onClick={handleExpireCheck}>检查超时</Button>
      </Space>
    }>
      <Tabs items={[
        {
          key: 'pending',
          label: <><Badge count={pending.length} offset={[10, 0]}><WarningOutlined /></Badge> 待审批 ({pending.length})</>,
          children: (
            <>
              {stats && (
                <Row gutter={16} style={{ marginBottom: 16 }}>
                  <Col span={4}><Statistic title="待审批" value={stats.pending || 0} /></Col>
                  <Col span={4}><Statistic title="高风险" value={stats.pending_by_risk?.high || 0} valueStyle={{ color: '#cf1322' }} /></Col>
                  <Col span={4}><Statistic title="极高风险" value={stats.pending_by_risk?.critical || 0} valueStyle={{ color: '#722ed1' }} /></Col>
                </Row>
              )}
              <Alert type="warning" message="高风险操作需要审批后才能自动执行，请仔细审核命令内容" style={{ marginBottom: 16 }} />
              <Table dataSource={pending} columns={pendingColumns} rowKey="id" loading={loading} scroll={{ x: 1200 }} />
            </>
          ),
        },
        {
          key: 'history',
          label: <><HistoryOutlined /> 审批历史</>,
          children: (
            <>
              {stats && (
                <Row gutter={16} style={{ marginBottom: 16 }}>
                  <Col span={4}><Statistic title="总计" value={stats.total || 0} /></Col>
                  <Col span={4}><Statistic title="已通过" value={stats.approved || 0} valueStyle={{ color: '#3f8600' }} /></Col>
                  <Col span={4}><Statistic title="已拒绝" value={stats.rejected || 0} valueStyle={{ color: '#cf1322' }} /></Col>
                  <Col span={4}><Statistic title="已超时" value={stats.expired || 0} /></Col>
                </Row>
              )}
              <Table dataSource={history} columns={historyColumns} rowKey="id" scroll={{ x: 1100 }} />
            </>
          ),
        },
      ]} />

      {/* 审批通过弹窗 */}
      <Modal title="审批通过" open={approveModalVisible} onCancel={() => setApproveModalVisible(false)} footer={null}>
        {selectedApproval && (
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="步骤">{selectedApproval.step_description}</Descriptions.Item>
            <Descriptions.Item label="命令"><code>{selectedApproval.command_preview}</code></Descriptions.Item>
            <Descriptions.Item label="风险等级">{getRiskTag(selectedApproval.risk_level).text}</Descriptions.Item>
            {selectedApproval.rollback_preview && (
              <Descriptions.Item label="回滚命令"><code>{selectedApproval.rollback_preview}</code></Descriptions.Item>
            )}
          </Descriptions>
        )}
        <Form form={approveForm} onFinish={handleApprove} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="comment" label="审批备注">
            <TextArea rows={3} placeholder="可选备注" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block icon={<CheckOutlined />}>确认通过并执行</Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 拒绝弹窗 */}
      <Modal title="拒绝执行" open={rejectModalVisible} onCancel={() => setRejectModalVisible(false)} footer={null}>
        <Alert type="error" message="拒绝后该步骤将被跳过，Runbook继续执行下一步" style={{ marginBottom: 16 }} />
        <Form form={rejectForm} onFinish={handleReject} layout="vertical">
          <Form.Item name="reason" label="拒绝原因" rules={[{ required: true, message: '请输入拒绝原因' }]}>
            <TextArea rows={3} placeholder="请说明拒绝原因" />
          </Form.Item>
          <Form.Item>
            <Button danger type="primary" htmlType="submit" block icon={<CloseOutlined />}>确认拒绝</Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 详情弹窗 */}
      <Modal title="审批详情" open={detailModalVisible} onCancel={() => setDetailModalVisible(false)} footer={null} width={700}>
        {selectedApproval && (
          <Descriptions bordered column={2}>
            <Descriptions.Item label="ID">{selectedApproval.id}</Descriptions.Item>
            <Descriptions.Item label="Runbook">{selectedApproval.runbook_id}</Descriptions.Item>
            <Descriptions.Item label="告警ID">{selectedApproval.alarm_id}</Descriptions.Item>
            <Descriptions.Item label="步骤">{selectedApproval.step_index}</Descriptions.Item>
            <Descriptions.Item label="步骤描述" span={2}>{selectedApproval.step_description}</Descriptions.Item>
            <Descriptions.Item label="动作类型">{selectedApproval.action_type}</Descriptions.Item>
            <Descriptions.Item label="风险等级">{getRiskTag(selectedApproval.risk_level).text}</Descriptions.Item>
            <Descriptions.Item label="命令预览" span={2}><pre style={{ margin: 0, background: '#f5f5f5', padding: 8 }}>{selectedApproval.command_preview}</pre></Descriptions.Item>
            {selectedApproval.rollback_preview && (
              <Descriptions.Item label="回滚命令" span={2}><pre style={{ margin: 0, background: '#f5f5f5', padding: 8 }}>{selectedApproval.rollback_preview}</pre></Descriptions.Item>
            )}
            <Descriptions.Item label="所需审批级别">{selectedApproval.required_level}</Descriptions.Item>
            <Descriptions.Item label="状态">{getStatusTag(selectedApproval.status).text}</Descriptions.Item>
            <Descriptions.Item label="过期时间">{selectedApproval.expires_at?.slice(0, 19)}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{selectedApproval.created_at?.slice(0, 19)}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </Card>
  );
};

export default RunbookApprovalPage;