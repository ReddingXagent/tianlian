/**
 * 告警自愈引擎 - 执行历史页面
 *
 * 功能：
 * 1. 自愈执行记录列表
 * 2. 执行详情查看（步骤时间线）
 * 3. 重试失败执行
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Space, Select, Drawer, Descriptions,
  Steps, Alert, Badge, Empty, message, Divider, Typography,
  Popconfirm, Statistic, Row, Col, Progress, Tooltip,
} from 'antd';
import {
  HistoryOutlined, ReloadOutlined, EyeOutlined,
  CheckCircleOutlined, CloseCircleOutlined, SyncOutlined,
  ClockCircleOutlined, ToolOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import healingApi, { HealingExecution, HealingExecutionDetail } from '../../api/healing';

const { Text } = Typography;

const statusColor: Record<string, string> = {
  pending_approval: 'orange',
  approved: 'blue',
  running: 'processing',
  success: 'success',
  partial_success: 'warning',
  failed: 'error',
  rejected: 'default',
  timeout: 'default',
  cooldown: 'default',
};

const statusText: Record<string, string> = {
  pending_approval: '待审批',
  approved: '已审批',
  running: '执行中',
  success: '成功',
  partial_success: '部分成功',
  failed: '失败',
  rejected: '已拒绝',
  timeout: '超时',
  cooldown: '冷却中',
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

const formatDuration = (ms: number): string => {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}min`;
};

const History: React.FC = () => {
  const [executions, setExecutions] = useState<HealingExecution[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filterStatus, setFilterStatus] = useState<string | undefined>(undefined);
  const [detail, setDetail] = useState<HealingExecutionDetail | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);
  const [stats, setStats] = useState<any>(null);

  const loadExecutions = useCallback(async (p = page) => {
    setLoading(true);
    try {
      const res = await healingApi.listExecutions({
        status: filterStatus,
        page: p,
        page_size: 20,
      });
      setExecutions(Array.isArray(res.items) ? res.items : []);
      setTotal(res.total || 0);
      setPage(p);
    } catch {
      message.error('加载执行记录失败');
    } finally {
      setLoading(false);
    }
  }, [filterStatus, page]);

  const loadStats = useCallback(async () => {
    try {
      const res = await healingApi.getStats();
      setStats(res);
    } catch {
      // 静默
    }
  }, []);

  useEffect(() => { loadExecutions(1); }, [filterStatus]);
  useEffect(() => { loadStats(); }, []);

  const handleViewDetail = async (id: number) => {
    try {
      const res = await healingApi.getExecution(id);
      setDetail(res);
      setDetailVisible(true);
    } catch {
      message.error('加载详情失败');
    }
  };

  const handleRetry = async (id: number) => {
    try {
      await healingApi.retryExecution(id);
      message.success('重试执行完成');
      loadExecutions(page);
      loadStats();
    } catch (err: any) {
      message.error(err?.response?.data?.message || '重试失败');
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
      width: 150,
      render: (name: string) => name || '-',
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
      title: '耗时',
      dataIndex: 'total_duration_ms',
      key: 'duration',
      width: 80,
      render: (ms: number) => formatDuration(ms),
    },
    {
      title: '步骤',
      key: 'steps',
      width: 120,
      render: (_: any, record: HealingExecution) => (
        <Space>
          {record.success_steps > 0 && <Tag color="success">{record.success_steps}成功</Tag>}
          {record.failed_steps > 0 && <Tag color="error">{record.failed_steps}失败</Tag>}
          {record.retry_count > 0 && <Tag color="blue">重试{record.retry_count}次</Tag>}
        </Space>
      ),
    },
    {
      title: '审批',
      dataIndex: 'approved_by',
      key: 'approved_by',
      width: 90,
      render: (v: string) => v ? (v === 'auto' ? <Tag color="green">自动</Tag> : v) : '-',
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
      width: 140,
      render: (_: any, record: HealingExecution) => (
        <Space>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleViewDetail(record.id)}>
            详情
          </Button>
          {['failed', 'partial_success'].includes(record.status) && (
            <Popconfirm title="确认重试？" onConfirm={() => handleRetry(record.id)}>
              <Button type="link" size="small" icon={<SyncOutlined />}>重试</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      {/* 统计面板 */}
      {stats && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={4}>
            <Card size="small">
              <Statistic title="总执行" value={stats.total} suffix="次" valueStyle={{ fontSize: 20 }} prefix={<ThunderboltOutlined />} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic
                title="成功率"
                value={stats.success_rate}
                suffix="%"
                valueStyle={{ fontSize: 20, color: stats.success_rate >= 80 ? '#3f8600' : '#cf1322' }}
                prefix={<CheckCircleOutlined />}
              />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="平均耗时" value={stats.average_duration_ms} suffix="ms" valueStyle={{ fontSize: 20 }} prefix={<ClockCircleOutlined />} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="自动审批率" value={stats.auto_approve_rate} suffix="%" valueStyle={{ fontSize: 20 }} prefix={<ToolOutlined />} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="待审批" value={stats.pending_approvals} suffix="条" valueStyle={{ fontSize: 20, color: stats.pending_approvals > 0 ? '#fa8c16' : undefined }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic
                title="状态分布"
                valueRender={() => (
                  <Space size={4} wrap>
                    {Object.entries(stats.status_breakdown || {}).map(([k, v]) => (
                      <Tag key={k} color={statusColor[k]}>{statusText[k] || k}: {v as number}</Tag>
                    ))}
                  </Space>
                )}
              />
            </Card>
          </Col>
        </Row>
      )}

      <Card
        title={<Space><HistoryOutlined /> 执行历史</Space>}
        extra={
          <Space>
            <Select
              style={{ width: 130 }}
              allowClear
              placeholder="状态筛选"
              value={filterStatus}
              onChange={setFilterStatus}
              options={Object.entries(statusText).map(([k, v]) => ({ value: k, label: v }))}
            />
            <Button icon={<ReloadOutlined />} onClick={() => { loadExecutions(1); loadStats(); }}>刷新</Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={executions}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize: 20,
            total,
            onChange: (p) => loadExecutions(p),
            showTotal: (t) => `共 ${t} 条`,
          }}
          size="middle"
          locale={{ emptyText: <Empty description="暂无执行记录" /> }}
        />
      </Card>

      {/* 执行详情抽屉 */}
      <Drawer
        title={`执行详情 #${detail?.id || ''}`}
        width={720}
        open={detailVisible}
        onClose={() => setDetailVisible(false)}
      >
        {detail && (
          <>
            <Descriptions column={2} size="small" bordered style={{ marginBottom: 16 }}>
              <Descriptions.Item label="规则">{detail.rule_name}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Badge status={(statusColor[detail.status] || 'default') as any} text={statusText[detail.status]} />
              </Descriptions.Item>
              <Descriptions.Item label="故障类型">{detail.fault_type}</Descriptions.Item>
              <Descriptions.Item label="耗时">{formatDuration(detail.total_duration_ms)}</Descriptions.Item>
              <Descriptions.Item label="告警ID">#{detail.alarm_id}</Descriptions.Item>
              <Descriptions.Item label="设备ID">{detail.device_id}</Descriptions.Item>
              <Descriptions.Item label="Runbook">{detail.runbook_template || '自动匹配'}</Descriptions.Item>
              <Descriptions.Item label="Runbook ID"><Text code>{detail.runbook_id || '-'}</Text></Descriptions.Item>
              <Descriptions.Item label="审批人">{detail.approved_by === 'auto' ? '自动' : (detail.approved_by || '-')}</Descriptions.Item>
              <Descriptions.Item label="重试次数">{detail.retry_count}</Descriptions.Item>
            </Descriptions>

            {detail.result && (
              <Alert
                message="执行结果"
                description={detail.result}
                type={detail.status === 'success' ? 'success' : detail.status === 'failed' ? 'error' : 'warning'}
                showIcon
                style={{ marginBottom: 16 }}
              />
            )}

            {detail.error_message && (
              <Alert
                message="错误信息"
                description={detail.error_message}
                type="error"
                showIcon
                style={{ marginBottom: 16 }}
              />
            )}

            {detail.reject_reason && (
              <Alert
                message="拒绝原因"
                description={detail.reject_reason}
                type="warning"
                showIcon
                style={{ marginBottom: 16 }}
              />
            )}

            {Array.isArray(detail.steps) && detail.steps.length > 0 && (
              <>
                <Divider>执行步骤</Divider>
                <Steps direction="vertical" size="small" items={
                  detail.steps.map((s: any, idx: number) => ({
                    title: (
                      <Space>
                        <Tag color={riskColor[s.risk_level] || 'default'}>{riskText[s.risk_level] || s.risk_level}</Tag>
                        <Tag>{actionTypeText[s.action_type] || s.action_type}</Tag>
                        {s.auto_execute ? <Tag color="blue">自动</Tag> : <Tag color="orange">人工</Tag>}
                      </Space>
                    ),
                    description: (
                      <div>
                        <Text>{s.description}</Text>
                        {s.command && <div><Text type="secondary" code style={{ fontSize: 12 }}>{s.command}</Text></div>}
                        {s.result && <div style={{ marginTop: 4 }}><Text type="secondary">{s.result}</Text></div>}
                        {s.error_message && <div style={{ marginTop: 4 }}><Text type="danger">{s.error_message}</Text></div>}
                        {s.duration_ms > 0 && <Text type="secondary" style={{ marginLeft: 8 }}>{s.duration_ms}ms</Text>}
                      </div>
                    ),
                    status: (statusColor[s.status] || 'wait') as any,
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

export default History;
