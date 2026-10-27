/**
 * 告警自愈引擎 - 审批管理页面
 *
 * 功能：
 * 1. 待审批列表
 * 2. 审批/拒绝操作
 * 3. 审批历史
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Space, Modal, Input, Badge,
  Popconfirm, message, Descriptions, Empty, Typography,
  Alert, Tabs, Drawer, Steps, Divider,
} from 'antd';
import {
  AuditOutlined, CheckOutlined, CloseOutlined,
  EyeOutlined, ReloadOutlined, SafetyCertificateOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import healingApi, { HealingExecution, HealingExecutionDetail } from '../../api/healing';
import { fetchAllPages } from '../../api/fetchAll';

const { TextArea } = Input;
const { Text } = Typography;

const statusColor: Record<string, string> = {
  pending_approval: 'orange',
  approved: 'blue',
  running: 'processing',
  success: 'success',
  partial_success: 'warning',
  failed: 'error',
  rejected: 'default',
};

const statusText: Record<string, string> = {
  pending_approval: '待审批',
  approved: '已审批',
  running: '执行中',
  success: '成功',
  partial_success: '部分成功',
  failed: '失败',
  rejected: '已拒绝',
};

const riskColor: Record<string, string> = {
  low: 'green',
  medium: 'orange',
  high: 'red',
  critical: 'magenta',
};

const riskText: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
  critical: '极高',
};

const actionTypeText: Record<string, string> = {
  remote_command: '远程命令',
  api_call: 'API调用',
  config_change: '配置变更',
  restart_service: '重启服务',
  reset_parameter: '重置参数',
  clear_cache: '清除缓存',
  create_workorder: '创建工单',
  send_notification: '发送通知',
  wait_and_recheck: '等待重检',
};

const Approvals: React.FC = () => {
  const [pending, setPending] = useState<HealingExecution[]>([]);
  const [history, setHistory] = useState<HealingExecution[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('pending');
  const [rejectModalVisible, setRejectModalVisible] = useState(false);
  const [rejectTarget, setRejectTarget] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [detail, setDetail] = useState<HealingExecutionDetail | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);

  const loadPending = useCallback(async () => {
    setLoading(true);
    try {
      const items = await fetchAllPages<HealingExecution>((params) => healingApi.listExecutions({
        status: 'pending_approval',
        page: params.page as number,
        page_size: params.page_size as number,
      }));
      setPending(Array.isArray(items) ? items : []);
    } catch {
      message.error('加载待审批列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    try {
      // 加载已审批、已拒绝、成功的记录
      const [approved, rejected, success] = await Promise.all([
        healingApi.listExecutions({ status: 'approved', page: 1, page_size: 50 }).catch(() => ({ items: [], total: 0 })),
        healingApi.listExecutions({ status: 'rejected', page: 1, page_size: 50 }).catch(() => ({ items: [], total: 0 })),
        healingApi.listExecutions({ status: 'success', page: 1, page_size: 50 }).catch(() => ({ items: [], total: 0 })),
      ]);
      const all = [
        ...(Array.isArray(approved.items) ? approved.items : []),
        ...(Array.isArray(rejected.items) ? rejected.items : []),
        ...(Array.isArray(success.items) ? success.items : []),
      ].sort((a, b) => {
        const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
        const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
        return tb - ta;
      });
      setHistory(all);
    } catch {
      // 静默
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadPending(); }, [loadPending]);

  const handleApprove = async (id: number) => {
    try {
      await healingApi.approveExecution(id);
      message.success('审批通过，已开始执行');
      loadPending();
    } catch (err: any) {
      message.error(err?.response?.data?.message || '审批失败');
    }
  };

  const handleReject = async () => {
    if (!rejectTarget) return;
    try {
      await healingApi.rejectExecution(rejectTarget, rejectReason);
      message.success('已拒绝执行');
      setRejectModalVisible(false);
      setRejectReason('');
      setRejectTarget(null);
      loadPending();
    } catch (err: any) {
      message.error(err?.response?.data?.message || '拒绝失败');
    }
  };

  const handleViewDetail = async (id: number) => {
    try {
      const res = await healingApi.getExecution(id);
      setDetail(res);
      setDetailVisible(true);
    } catch {
      message.error('加载详情失败');
    }
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60,
      render: (id: number) => <Text code>#{id}</Text>,
    },
    {
      title: '规则',
      dataIndex: 'rule_name',
      key: 'rule_name',
      width: 140,
    },
    {
      title: '故障类型',
      dataIndex: 'fault_type',
      key: 'fault_type',
      width: 140,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Badge
          status={(statusColor[status] || 'default') as any}
          text={statusText[status] || status}
        />
      ),
    },
    {
      title: '触发时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: HealingExecution) => (
        <Space>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleViewDetail(record.id)}>
            详情
          </Button>
          {record.status === 'pending_approval' && (
            <>
              <Popconfirm
                title="确认审批通过？"
                description="审批后将自动执行Runbook修复步骤"
                onConfirm={() => handleApprove(record.id)}
                okText="通过"
                cancelText="取消"
              >
                <Button type="link" size="small" style={{ color: '#34a853' }} icon={<CheckOutlined />}>
                  通过
                </Button>
              </Popconfirm>
              <Button
                type="link"
                size="small"
                danger
                icon={<CloseOutlined />}
                onClick={() => {
                  setRejectTarget(record.id);
                  setRejectModalVisible(true);
                }}
              >
                拒绝
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card
        title={
          <Space>
            <AuditOutlined />
            <span>审批管理</span>
            {pending.length > 0 && <Badge count={pending.length} />}
          </Space>
        }
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => { loadPending(); loadHistory(); }}>刷新</Button>
        }
      >
        {pending.length > 0 && (
          <Alert
            message={`有 ${pending.length} 条自愈执行等待审批`}
            description="高风险操作需要人工确认后才会执行。请仔细审查后决定通过或拒绝。"
            type="warning"
            showIcon
            icon={<ExclamationCircleOutlined />}
            style={{ marginBottom: 16 }}
          />
        )}

        <Tabs activeKey={activeTab} onChange={(key) => { setActiveTab(key); if (key === 'history') loadHistory(); }} items={[
          {
            key: 'pending',
            label: <span><SafetyCertificateOutlined /> 待审批 ({pending.length})</span>,
            children: (
              <Table
                columns={columns}
                dataSource={pending}
                rowKey="id"
                loading={loading}
                pagination={false}
                size="middle"
                locale={{ emptyText: <Empty description="暂无待审批记录" /> }}
              />
            ),
          },
          {
            key: 'history',
            label: '审批历史',
            children: (
              <Table
                columns={columns}
                dataSource={history}
                rowKey="id"
                loading={loading}
                pagination={{ pageSize: 20 }}
                size="middle"
                locale={{ emptyText: <Empty description="暂无审批历史" /> }}
              />
            ),
          },
        ]} />
      </Card>

      {/* 拒绝原因弹窗 */}
      <Modal
        title="拒绝自愈执行"
        open={rejectModalVisible}
        onCancel={() => { setRejectModalVisible(false); setRejectReason(''); }}
        onOk={handleReject}
        okText="确认拒绝"
        okButtonProps={{ danger: true }}
      >
        <div style={{ padding: '8px 0' }}>
          <Text>拒绝原因：</Text>
          <TextArea
            rows={3}
            placeholder="请输入拒绝原因"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            style={{ marginTop: 8 }}
          />
        </div>
      </Modal>

      {/* 执行详情抽屉 */}
      <Drawer
        title={`执行详情 #${detail?.id || ''}`}
        width={720}
        open={detailVisible}
        onClose={() => setDetailVisible(false)}
      >
        {detail && (
          <>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="规则">{detail.rule_name}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Badge status={(statusColor[detail.status] || 'default') as any} text={statusText[detail.status]} />
              </Descriptions.Item>
              <Descriptions.Item label="故障类型">{detail.fault_type}</Descriptions.Item>
              <Descriptions.Item label="Runbook">{detail.runbook_template || '自动匹配'}</Descriptions.Item>
              <Descriptions.Item label="告警ID">#{detail.alarm_id}</Descriptions.Item>
              <Descriptions.Item label="设备ID">{detail.device_id}</Descriptions.Item>
            </Descriptions>

            {detail.error_message && (
              <Alert message="错误信息" description={detail.error_message} type="error" showIcon style={{ marginTop: 16 }} />
            )}

            {detail.reject_reason && (
              <Alert message="拒绝原因" description={detail.reject_reason} type="warning" showIcon style={{ marginTop: 16 }} />
            )}

            {Array.isArray(detail.steps) && detail.steps.length > 0 && (
              <>
                <Divider>执行步骤</Divider>
                <Steps direction="vertical" size="small" items={
                  detail.steps.map((s: any) => ({
                    title: (
                      <Space>
                        <Tag color={riskColor[s.risk_level] || 'default'}>{riskText[s.risk_level]}</Tag>
                        <Tag>{actionTypeText[s.action_type] || s.action_type}</Tag>
                      </Space>
                    ),
                    description: (
                      <div>
                        <Text>{s.description}</Text>
                        {s.command && <div><Text type="secondary" code style={{ fontSize: 12 }}>{s.command}</Text></div>}
                      </div>
                    ),
                    status: 'finish' as const,
                  }))
                } />
              </>
            )}
          </>
        )}
      </Drawer>
    </div>
  );
};

export default Approvals;
