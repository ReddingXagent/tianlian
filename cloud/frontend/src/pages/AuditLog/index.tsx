/**
 * 审计日志页 - 用户操作全记录
 */
import React, { useEffect, useState, useMemo } from 'react';
import { Card, Table, Tag, Button, Space, Select, message, Row, Col, Statistic, Input, Spin } from 'antd';
import { SearchOutlined, ReloadOutlined, HistoryOutlined, LoginOutlined, FileAddOutlined, EditOutlined, DeleteOutlined, ExportOutlined } from '@ant-design/icons';
import api from '../../api';
import { useTranslation } from 'react-i18next';

interface LogItem {
  id: number;
  timestamp: string;
  username: string;
  user_role: string;
  action: string;
  module: string;
  target_id: string | null;
  target_desc: string | null;
  detail: string | null;
  ip_address: string | null;
  result: string;
  error_msg: string | null;
}

const AuditLogPage: React.FC = () => {
  const { t } = useTranslation();

  const ACTION_CONFIG: Record<string, { color: string; icon: React.ReactNode; text: string }> = {
    login: { color: 'blue', icon: <LoginOutlined />, text: t('pages.auditLog.action_login') },
    logout: { color: 'default', icon: <LoginOutlined />, text: t('pages.auditLog.action_logout') },
    create: { color: 'green', icon: <FileAddOutlined />, text: t('pages.auditLog.action_create') },
    update: { color: 'orange', icon: <EditOutlined />, text: t('pages.auditLog.action_update') },
    delete: { color: 'red', icon: <DeleteOutlined />, text: t('pages.auditLog.action_delete') },
    export: { color: 'purple', icon: <ExportOutlined />, text: t('pages.auditLog.action_export') },
    dispatch: { color: 'cyan', icon: <HistoryOutlined />, text: t('pages.auditLog.action_dispatch') },
  };

  const MODULE_MAP: Record<string, string> = {
    auth: t('pages.auditLog.module_auth'), users: t('pages.auditLog.module_users'), stations: t('pages.auditLog.module_stations'), devices: t('pages.auditLog.module_devices'),
    alarms: t('pages.auditLog.module_alarms'), workorders: t('pages.auditLog.module_workorders'), knowledge: t('pages.auditLog.module_knowledge'),
    reports: t('pages.auditLog.module_reports'), config: t('pages.auditLog.module_config'), gateways: t('pages.auditLog.module_gateways'), rbac: t('pages.auditLog.module_rbac'),
  };

  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<LogItem[]>([]);
  const [stats, setStats] = useState<any>({});
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [filterAction, setFilterAction] = useState('');
  const [filterModule, setFilterModule] = useState('');
  const [searchUser, setSearchUser] = useState('');
  const [filterResult, setFilterResult] = useState('');

  useEffect(() => { fetchLogs(); fetchStats(); }, []);
  useEffect(() => { fetchLogs(); }, [pagination.current, filterAction, filterModule, searchUser, filterResult]);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const params: any = { page: pagination.current, page_size: pagination.pageSize };
      if (filterAction) params.action = filterAction;
      if (filterModule) params.module = filterModule;
      if (searchUser) params.username = searchUser;
      if (filterResult) params.result = filterResult;
      const { data } = await api.get('/operation-log', { params });
      setItems(data.items || []);
      setPagination(p => ({ ...p, total: data.total || 0 }));
    } catch { message.error(t('pages.auditLog.load_failed')); }
    finally { setLoading(false); }
  };

  const fetchStats = async () => {
    try {
      const { data } = await api.get('/operation-log/stats');
      setStats(data || {});
    } catch { /* ignore */ }
  };

  const columns = [
    { title: '时间', dataIndex: 'timestamp', key: 'timestamp', width: 170,
      render: (t: string) => t ? new Date(t).toLocaleString() : '-' },
    { title: '用户', dataIndex: 'username', key: 'username', width: 100 },
    {
      title: '操作', dataIndex: 'action', key: 'action', width: 90,
      render: (a: string) => {
        const cfg = ACTION_CONFIG[a] || { color: 'default', icon: null, text: a };
        return <Tag color={cfg.color}>{cfg.icon} {cfg.text}</Tag>;
      },
    },
    {
      title: '模块', dataIndex: 'module', key: 'module', width: 80,
      render: (m: string) => MODULE_MAP[m] || m || '-',
    },
    { title: '目标', dataIndex: 'target_desc', key: 'target_desc', ellipsis: true,
      render: (t: string, r: LogItem) => t || r.target_id || '-' },
    { title: '详情', dataIndex: 'detail', key: 'detail', ellipsis: true },
    { title: 'IP', dataIndex: 'ip_address', key: 'ip_address', width: 130 },
    {
      title: '结果', dataIndex: 'result', key: 'result', width: 70,
      render: (r: string) => r === 'success'
        ? <Tag color="green">成功</Tag>
        : <Tag color="red">失败</Tag>,
    },
  ];

  return (
    <div className="page-container">
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card hoverable>
            <Statistic title="总日志" value={stats.total_logs || 0} prefix={<HistoryOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable>
            <Statistic title="今日" value={stats.today_logs || 0} prefix={<HistoryOutlined />} valueStyle={{ color: '#ff5a36' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable>
            <Statistic title="失败操作" value={stats.failed_logs || 0} prefix={<DeleteOutlined />} valueStyle={{ color: (stats.failed_logs || 0) > 0 ? '#cf1322' : '#3f8600' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable>
            <Statistic title="登录记录" value={stats.by_action?.login || 0} prefix={<LoginOutlined />} />
          </Card>
        </Col>
      </Row>

      <Card
        title={<Space><HistoryOutlined />操作审计日志</Space>}
        extra={
          <Space>
            <Select placeholder="操作类型" allowClear style={{ width: 110 }} value={filterAction || undefined}
              onChange={(v) => { setFilterAction(v || ''); setPagination(p => ({ ...p, current: 1 })); }}>
              {Object.entries(ACTION_CONFIG).map(([k, v]) => (
                <Select.Option key={k} value={k}>{v.text}</Select.Option>
              ))}
            </Select>
            <Select placeholder="模块" allowClear style={{ width: 100 }} value={filterModule || undefined}
              onChange={(v) => { setFilterModule(v || ''); setPagination(p => ({ ...p, current: 1 })); }}>
              {Object.entries(MODULE_MAP).map(([k, v]) => (
                <Select.Option key={k} value={k}>{v}</Select.Option>
              ))}
            </Select>
            <Select placeholder="结果" allowClear style={{ width: 90 }} value={filterResult || undefined}
              onChange={(v) => { setFilterResult(v || ''); setPagination(p => ({ ...p, current: 1 })); }}>
              <Select.Option value="success">成功</Select.Option>
              <Select.Option value="failure">失败</Select.Option>
            </Select>
            <Input placeholder="搜索用户" prefix={<SearchOutlined />} style={{ width: 130 }}
              value={searchUser} onChange={e => setSearchUser(e.target.value)}
              onPressEnter={() => fetchLogs()} />
            <Button icon={<ReloadOutlined />} onClick={() => { fetchLogs(); fetchStats(); }}>刷新</Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={items}
          rowKey="id"
          loading={loading}
          size="small"
          pagination={{
            ...pagination,
            showTotal: (t) => `共 ${t} 条`,
            showSizeChanger: false,
            onChange: (page) => setPagination(p => ({ ...p, current: page })),
          }}
          scroll={{ x: 900 }}
        />
      </Card>
    </div>
  );
};

export default AuditLogPage;