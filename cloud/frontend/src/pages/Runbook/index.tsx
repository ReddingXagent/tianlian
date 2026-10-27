/**
 * Runbook自动化执行页面
 *
 * 功能:
 * 1. Runbook模板库浏览
 * 2. 为告警执行Runbook(手动触发)
 * 3. 执行记录查询与详情
 * 4. Runbook执行统计
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Tabs, Tag, Button, Space, Modal, Descriptions,
  Timeline, Statistic, Row, Col, Select, InputNumber, message,
  Alert, Empty, Badge, Popconfirm, Tooltip, Drawer, Steps,
  Progress, Typography, Divider
} from 'antd';
import {
  PlayCircleOutlined, ClockCircleOutlined, FileTextOutlined,
  ToolOutlined, BarChartOutlined, ReloadOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined,
  EyeOutlined
} from '@ant-design/icons';
import runbookApi, { RunbookTemplate, RunbookExecution, RunbookStats, RunbookExecutionDetail } from '../../api/runbook';

const { Text } = Typography;

// ========= 工具函数 =========

const statusColor: Record<string, string> = {
  completed: 'success',
  running: 'processing',
  failed: 'error',
  pending: 'default',
  skipped: 'warning',
  rolled_back: 'error',
};

const statusText: Record<string, string> = {
  completed: '成功',
  running: '执行中',
  failed: '失败',
  pending: '待处理',
  skipped: '跳过',
  rolled_back: '已回滚',
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

const categoryText: Record<string, string> = {
  inverter: '逆变器',
  charger: '充电桩',
  general: '通用',
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
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}min`;
};

// ========= 组件 =========

const RunbookPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('templates');
  const [templates, setTemplates] = useState<RunbookTemplate[]>([]);
  const [templateDetail, setTemplateDetail] = useState<any>(null);
  const [templateDrawerVisible, setTemplateDrawerVisible] = useState(false);
  const [executions, setExecutions] = useState<RunbookExecution[]>([]);
  const [executionDetail, setExecutionDetail] = useState<RunbookExecutionDetail | null>(null);
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [stats, setStats] = useState<RunbookStats | null>(null);
  const [execLoading, setExecLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filterCategory, setFilterCategory] = useState<string | undefined>(undefined);
  const [filterStatus, setFilterStatus] = useState<string | undefined>(undefined);

  // 加载模板
  const loadTemplates = useCallback(async () => {
    try {
      const res = await runbookApi.listTemplates(filterCategory);
      setTemplates(Array.isArray(res) ? res : []);
    } catch {
      message.error('加载模板失败');
    }
  }, [filterCategory]);

  // 加载执行记录
  const loadExecutions = useCallback(async (p = page) => {
    setExecLoading(true);
    try {
      const res = await runbookApi.listExecutions({
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
      setExecLoading(false);
    }
  }, [filterStatus, page]);

  // 加载统计
  const loadStats = useCallback(async () => {
    try {
      const res = await runbookApi.getStats();
      setStats(res);
    } catch {
      // 无数据时静默
    }
  }, []);

  useEffect(() => { loadTemplates(); }, [loadTemplates]);
  useEffect(() => { loadExecutions(1); }, [loadExecutions]);
  useEffect(() => { loadStats(); }, [loadStats]);

  // 查看模板详情
  const handleViewTemplate = async (name: string) => {
    try {
      const res = await runbookApi.getTemplate(name);
      setTemplateDetail(res);
      setTemplateDrawerVisible(true);
    } catch {
      message.error('加载模板详情失败');
    }
  };

  // 为告警执行Runbook
  const handleExecute = async (alarmId: number) => {
    try {
      const res = await runbookApi.execute(alarmId, false);
      message.success(`Runbook执行完成: ${res.runbook_id || ''}`);
      loadExecutions(1);
      loadStats();
    } catch (err: any) {
      message.error(err?.response?.data?.message || '执行失败');
    }
  };

  // Dry Run
  const handleDryRun = async (alarmId: number) => {
    try {
      const res = await runbookApi.execute(alarmId, true);
      message.info(`Dry Run完成: ${res.runbook_id || ''}，未实际执行`);
      loadExecutions(1);
    } catch (err: any) {
      message.error(err?.response?.data?.message || 'Dry Run失败');
    }
  };

  // 查看执行详情
  const handleViewExecution = async (id: number) => {
    try {
      const res = await runbookApi.getExecution(id);
      setExecutionDetail(res);
      setDetailDrawerVisible(true);
    } catch {
      message.error('加载执行详情失败');
    }
  };

  // 手动触发Runbook(通过输入告警ID)
  const [executeAlarmId, setExecuteAlarmId] = useState<number | undefined>(undefined);
  const [executeModalVisible, setExecuteModalVisible] = useState(false);

  // ========= Tabs =========
  const templateColumns = [
    {
      title: '模板名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: RunbookTemplate) => (
        <Space>
          <Tag color="blue">{categoryText[record.category] || record.category}</Tag>
          <Text strong>{name}</Text>
        </Space>
      ),
    },
    { title: '描述', dataIndex: 'description', key: 'description', width: 200 },
    {
      title: '步骤数',
      key: 'steps',
      render: (_: any, record: RunbookTemplate) => (
        <Space>
          <Text>{record.step_count}</Text>
          <Text type="secondary">({record.auto_steps}自动/{record.manual_steps}人工)</Text>
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: RunbookTemplate) => (
        <Button type="link" icon={<EyeOutlined />} onClick={() => handleViewTemplate(record.name)}>
          查看详情
        </Button>
      ),
    },
  ];

  const executionColumns = [
    {
      title: 'Runbook ID',
      dataIndex: 'runbook_id',
      key: 'runbook_id',
      render: (id: string) => <Text code>{id?.split('-').slice(0, 3).join('-')}</Text>,
    },
    { title: '故障类型', dataIndex: 'fault_type', key: 'fault_type', width: 160 },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => <Badge status={(statusColor[status] || 'default') as 'default' | 'error' | 'warning' | 'success' | 'processing'} text={statusText[status] || status} />,
    },
    {
      title: '耗时',
      dataIndex: 'total_duration_ms',
      key: 'total_duration_ms',
      render: (ms: number) => formatDuration(ms || 0),
    },
    {
      title: '步骤',
      key: 'steps',
      render: (_: any, record: RunbookExecution) => (
        <Space>
          {record.success_steps > 0 && <Tag color="success">{record.success_steps}成功</Tag>}
          {record.failed_steps > 0 && <Tag color="error">{record.failed_steps}失败</Tag>}
          <Text type="secondary">{record.auto_executed}自动/{record.manual_required}人工</Text>
        </Space>
      ),
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: RunbookExecution) => (
        <Button type="link" icon={<EyeOutlined />} onClick={() => handleViewExecution(record.id)}>
          详情
        </Button>
      ),
    },
  ];

  // ========= 统计面板 =========
  const statsPanel = stats ? (
    <Row gutter={16} style={{ marginBottom: 16 }}>
      <Col span={6}>
        <Card>
          <Statistic title="总执行次数" value={stats.total_executions} suffix="次" prefix={<ToolOutlined />} />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title="成功率"
            value={stats.success_rate}
            suffix="%"
            valueStyle={{ color: stats.success_rate >= 90 ? '#3f8600' : stats.success_rate >= 70 ? '#f5a623' : '#cf1322' }}
            prefix={<CheckCircleOutlined />}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic title="平均耗时" value={stats.average_duration_ms} suffix="ms" prefix={<ClockCircleOutlined />} />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic title="近7天执行" value={stats.last_7_days} suffix="次" prefix={<BarChartOutlined />} />
        </Card>
      </Col>
    </Row>
  ) : null;

  // ========= 执行详情抽屉 =========
  const renderExecutionDetail = (detail: RunbookExecutionDetail) => (
    <div>
      <Descriptions column={2} size="small" bordered style={{ marginBottom: 16 }}>
        <Descriptions.Item label="Runbook ID"><Text code>{detail.runbook_id}</Text></Descriptions.Item>
        <Descriptions.Item label="状态">
          <Badge status={(statusColor[detail.status] || 'default') as 'default' | 'error' | 'warning' | 'success' | 'processing'} text={statusText[detail.status] || detail.status} />
        </Descriptions.Item>
        <Descriptions.Item label="故障类型">{detail.fault_type}</Descriptions.Item>
        <Descriptions.Item label="耗时">{formatDuration(detail.total_duration_ms || 0)}</Descriptions.Item>
        <Descriptions.Item label="告警ID">#{detail.alarm_id}</Descriptions.Item>
        <Descriptions.Item label="设备ID">{detail.device_id}</Descriptions.Item>
        <Descriptions.Item label="自动/人工">{detail.auto_executed}/{detail.manual_required}</Descriptions.Item>
        <Descriptions.Item label="成功/失败">{detail.success_steps}/{detail.failed_steps}</Descriptions.Item>
      </Descriptions>

      <Text strong>执行步骤:</Text>
      <Divider style={{ margin: '8px 0' }} />
      <Steps direction="vertical" size="small" items={
        (Array.isArray(detail.steps) ? detail.steps : []).map((s: any) => ({
          title: (
            <Space>
              <Tag color={riskColor[s.risk_level] || 'default'}>{riskText[s.risk_level]}</Tag>
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
          status: statusColor[s.status] as any,
        })) || []
      } />

      {detail.error_message && (
        <Alert
          message="执行错误"
          description={detail.error_message}
          type="error"
          showIcon
          style={{ marginTop: 16 }}
        />
      )}
    </div>
  );

  return (
    <div>
      {statsPanel}

      <Card
        title="Runbook 自动化执行"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => { loadTemplates(); loadExecutions(1); loadStats(); }}>
              刷新
            </Button>
            <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => setExecuteModalVisible(true)}>
              手动触发
            </Button>
          </Space>
        }
      >
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'templates',
            label: (
              <span><FileTextOutlined /> Runbook模板库</span>
            ),
            children: (
              <>
                <Space style={{ marginBottom: 12 }}>
                  <Text>筛选类别:</Text>
                  <Select
                    style={{ width: 150 }}
                    allowClear
                    placeholder="全部"
                    value={filterCategory}
                    onChange={setFilterCategory}
                    options={[
                      { value: 'inverter', label: '逆变器' },
                      { value: 'charger', label: '充电桩' },
                      { value: 'general', label: '通用' },
                    ]}
                  />
                </Space>
                <Table
                  columns={templateColumns}
                  dataSource={Array.isArray(templates) ? templates : []}
                  rowKey="name"
                  pagination={false}
                  locale={{ emptyText: <Empty description="暂无Runbook模板" /> }}
                />
              </>
            ),
          },
          {
            key: 'executions',
            label: (
              <span><ClockCircleOutlined /> 执行记录</span>
            ),
            children: (
              <>
                <Space style={{ marginBottom: 12 }}>
                  <Text>状态筛选:</Text>
                  <Select
                    style={{ width: 120 }}
                    allowClear
                    placeholder="全部"
                    value={filterStatus}
                    onChange={(v) => { setFilterStatus(v); }}
                    options={[
                      { value: 'completed', label: '成功' },
                      { value: 'failed', label: '失败' },
                      { value: 'running', label: '执行中' },
                    ]}
                  />
                </Space>
                <Table
                  columns={executionColumns}
                  dataSource={Array.isArray(executions) ? executions : []}
                  rowKey="id"
                  loading={execLoading}
                  pagination={{
                    current: page,
                    pageSize: 20,
                    total,
                    onChange: (p) => loadExecutions(p),
                  }}
                  locale={{ emptyText: <Empty description="暂无执行记录" /> }}
                />
              </>
            ),
          },
        ]} />
      </Card>

      {/* 模板详情抽屉 */}
      <Drawer
        title="Runbook模板详情"
        width={720}
        open={templateDrawerVisible}
        onClose={() => setTemplateDrawerVisible(false)}
      >
        {templateDetail && (
          <div>
            <Descriptions column={1} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="名称">{templateDetail.name}</Descriptions.Item>
              <Descriptions.Item label="类别">{categoryText[templateDetail.category] || templateDetail.category}</Descriptions.Item>
              <Descriptions.Item label="描述">{templateDetail.description}</Descriptions.Item>
              <Descriptions.Item label="步骤数">{templateDetail.step_count} (自动{templateDetail.auto_steps} / 人工{templateDetail.manual_steps})</Descriptions.Item>
            </Descriptions>
            <Text strong>执行步骤:</Text>
            <Divider style={{ margin: '8px 0' }} />
            <Steps direction="vertical" items={
              (Array.isArray(templateDetail.steps) ? templateDetail.steps : []).map((s: any) => ({
                title: (
                  <Space>
                    <Tag color={riskColor[s.risk_level] || 'default'}>{riskText[s.risk_level]}</Tag>
                    <Tag>{actionTypeText[s.action_type] || s.action_type}</Tag>
                    {s.auto_execute ? <Tag color="blue">自动</Tag> : <Tag color="orange">人工</Tag>}
                  </Space>
                ),
                description: (
                  <div>
                    <Text>{s.description}</Text>
                    {s.command && <div><Text type="secondary" code style={{ fontSize: 12 }}>{s.command}</Text></div>}
                    <Text type="secondary" style={{ marginLeft: 8 }}>超时 {s.timeout_sec}s</Text>
                  </div>
                ),
                status: 'finish' as const,
              })) || []
            } />
          </div>
        )}
      </Drawer>

      {/* 执行详情抽屉 */}
      <Drawer
        title="执行详情"
        width={720}
        open={detailDrawerVisible}
        onClose={() => setDetailDrawerVisible(false)}
      >
        {executionDetail && renderExecutionDetail(executionDetail)}
      </Drawer>

      {/* 手动触发Runbook弹窗 */}
      <Modal
        title="手动触发Runbook"
        open={executeModalVisible}
        onCancel={() => { setExecuteModalVisible(false); setExecuteAlarmId(undefined); }}
        footer={[
          <Button key="cancel" onClick={() => setExecuteModalVisible(false)}>取消</Button>,
          <Popconfirm
            key="dryrun"
            title="确认Dry Run?"
            description="Dry Run仅预览，不会实际执行修复"
            onConfirm={() => { if (executeAlarmId) handleDryRun(executeAlarmId); setExecuteModalVisible(false); }}
          >
            <Button>Dry Run</Button>
          </Popconfirm>,
          <Popconfirm
            key="exec"
            title="确认执行Runbook?"
            description="将自动执行修复步骤，请确认告警ID"
            onConfirm={() => { if (executeAlarmId) handleExecute(executeAlarmId); setExecuteModalVisible(false); }}
          >
            <Button type="primary">执行</Button>
          </Popconfirm>,
        ]}
      >
        <div style={{ padding: '16px 0' }}>
          <Text>输入告警ID以触发Runbook:</Text>
          <InputNumber
            style={{ width: '100%', marginTop: 8 }}
            min={1}
            placeholder="告警ID"
            value={executeAlarmId}
            onChange={(v) => setExecuteAlarmId(v || undefined)}
            onPressEnter={() => {
              if (executeAlarmId) handleExecute(executeAlarmId);
              setExecuteModalVisible(false);
            }}
          />
        </div>
      </Modal>
    </div>
  );
};

export default RunbookPage;
