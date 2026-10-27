/**
 * 天链 V3 - 系统配置：日志审计 Tab
 */
import React from 'react';
import {
  Card, Table, Button, Space, Tag, Input, Select, Row, Col, Statistic,
} from 'antd';
import {
  HistoryOutlined, ReloadOutlined, DeleteOutlined, LoginOutlined, SearchOutlined,
} from '@ant-design/icons';
import { useAuditLogs } from '../hooks/useAuditLogs';
import { ACTION_CONFIG, MODULE_MAP } from '../constants';
import type { LogItem } from '../types';

const AuditLogTab: React.FC = () => {
  const {
    logs, logsLoading, logStats, logPagination,
    filterAction, setFilterAction,
    filterModule, setFilterModule,
    searchUser, setSearchUser,
    fetchLogs, fetchLogStats,
  } = useAuditLogs();

  const logColumns = [
    {
      title: '时间', dataIndex: 'timestamp', key: 'timestamp', width: 170,
      render: (t: string) => t ? new Date(t).toLocaleString() : '-',
    },
    { title: '用户', dataIndex: 'username', key: 'username', width: 100 },
    {
      title: '操作', dataIndex: 'action', key: 'action', width: 90,
      render: (a: string) => {
        const cfg = ACTION_CONFIG[a] || { color: 'default', text: a };
        return <Tag color={cfg.color}>{cfg.text}</Tag>;
      },
    },
    {
      title: '模块', dataIndex: 'module', key: 'module', width: 80,
      render: (m: string) => MODULE_MAP[m] || m || '-',
    },
    {
      title: '目标', dataIndex: 'target_desc', key: 'target_desc', ellipsis: true,
      render: (t: string, r: LogItem) => t || r.target_id || '-',
    },
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
    <>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card hoverable size="small">
            <Statistic title="总日志" value={logStats.total_logs || 0} prefix={<HistoryOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable size="small">
            <Statistic title="今日" value={logStats.today_logs || 0} prefix={<HistoryOutlined />} valueStyle={{ color: '#ff5a36' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable size="small">
            <Statistic title="失败操作" value={logStats.failed_logs || 0} prefix={<DeleteOutlined />}
              valueStyle={{ color: (logStats.failed_logs || 0) > 0 ? '#cf1322' : '#3f8600' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable size="small">
            <Statistic title="登录记录" value={logStats.by_action?.login || 0} prefix={<LoginOutlined />} />
          </Card>
        </Col>
      </Row>

      <Card
        title={<Space><HistoryOutlined />操作审计日志</Space>}
        extra={
          <Space>
            <Select placeholder="操作类型" allowClear style={{ width: 110 }} value={filterAction || undefined}
              onChange={(v) => { setFilterAction(v || ''); fetchLogs(1); }}>
              {Object.entries(ACTION_CONFIG).map(([k, v]) => (
                <Select.Option key={k} value={k}>{v.text}</Select.Option>
              ))}
            </Select>
            <Select placeholder="模块" allowClear style={{ width: 100 }} value={filterModule || undefined}
              onChange={(v) => { setFilterModule(v || ''); fetchLogs(1); }}>
              {Object.entries(MODULE_MAP).map(([k, v]) => (
                <Select.Option key={k} value={k}>{v}</Select.Option>
              ))}
            </Select>
            <Input placeholder="搜索用户" prefix={<SearchOutlined />} style={{ width: 130 }}
              value={searchUser} onChange={e => setSearchUser(e.target.value)}
              onPressEnter={() => fetchLogs(1)} />
            <Button icon={<ReloadOutlined />} onClick={() => { fetchLogs(1); fetchLogStats(); }}>刷新</Button>
          </Space>
        }
      >
        <Table
          columns={logColumns}
          dataSource={logs}
          rowKey="id"
          loading={logsLoading}
          size="small"
          pagination={{
            ...logPagination,
            showTotal: (t) => `共 ${t} 条`,
            showSizeChanger: false,
            onChange: (page) => fetchLogs(page),
          }}
          scroll={{ x: 900 }}
        />
      </Card>
    </>
  );
};

export default AuditLogTab;
