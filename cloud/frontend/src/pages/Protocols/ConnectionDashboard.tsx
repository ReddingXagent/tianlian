/**
 * 天链V3 - 连接状态仪表板
 * 实时监控网关实例的连接状态概览
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Statistic, Table, Tag, Alert, Spin, Empty, Switch, Space, Typography, Progress
} from 'antd';
import {
  ReloadOutlined, CheckCircleOutlined, CloseCircleOutlined,
  SyncOutlined, ApiOutlined, SettingOutlined, ThunderboltOutlined,
  FileTextOutlined
} from '@ant-design/icons';
import { connectionDashboardAPI } from '../../api';
import type { ConnectionDashboard as DashboardData } from '../../types';

const { Text } = Typography;

// 自动轮询周期（毫秒）—— 验收要求"实时连接状态"，后端已有 REST 端点，采用轮询方案
export const REFRESH_INTERVAL = 10000;

const ConnectionDashboard: React.FC = () => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await connectionDashboardAPI.get();
      const d = (res.data)?.data || res.data;
      setData(d);
    } catch (err: unknown) {
      const msg = (err as any)?.response?.data?.message || (err as any)?.message || '加载失败';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  // 自动轮询：默认开启，卸载或关闭时清理定时器
  useEffect(() => {
    if (!autoRefresh) return;
    const timer = setInterval(fetchData, REFRESH_INTERVAL);
    return () => clearInterval(timer);
  }, [autoRefresh, fetchData]);

  const connColor = (status: string): string => {
    const map: Record<string, string> = { connected: '#34a853', disconnected: '#999', connecting: '#4285f4' };
    return map[status] || '#999';
  };

  const connLabel = (status: string): string => {
    const map: Record<string, string> = { connected: '已连接', disconnected: '未连接', connecting: '连接中' };
    return map[status] || status;
  };

  if (error) {
    return <Alert type="error" message={error} closable />;
  }

  if (loading && !data) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>;
  }

  const stats = data?.stats;
  const allCounts = [
    { label: '总实例', value: stats?.total || 0, color: '#4285f4', icon: <ApiOutlined /> },
    { label: '运行中', value: stats?.running || 0, color: '#34a853', icon: <CheckCircleOutlined /> },
    { label: '已连接', value: stats?.connected || 0, color: '#34a853', icon: <SyncOutlined /> },
    { label: '错误', value: stats?.error || 0, color: '#ea4335', icon: <CloseCircleOutlined /> },
  ];

  const recentColumns = [
    { title: '实例名称', dataIndex: 'name', key: 'name', width: 150 },
    { title: '协议类型', dataIndex: 'protocol_type', key: 'protocol_type', width: 100,
      render: (t: string) => <Tag>{t}</Tag> },
    {
      title: '连接状态', dataIndex: 'connection_status', key: 'connection_status', width: 100,
      render: (s: string) => (
        <Tag icon={s === 'connected' ? <CheckCircleOutlined /> : s === 'connecting' ? <SyncOutlined spin /> : <CloseCircleOutlined />}
          color={s === 'connected' ? 'green' : s === 'connecting' ? 'blue' : 'default'}>
          {connLabel(s)}
        </Tag>
      ),
    },
    {
      title: '最后连接', dataIndex: 'last_connected', key: 'last_connected', width: 170,
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
  ];

  return (
    <div>
      {/* 状态概览卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {allCounts.map(item => (
          <Col span={6} key={item.label}>
            <Card size="small">
              <Statistic title={item.label} value={item.value} valueStyle={{ color: item.color }} prefix={item.icon} />
            </Card>
          </Col>
        ))}
      </Row>

      {/* 详细统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card size="small" title={<span><ApiOutlined /> 协议分布</span>}>
            {stats?.by_protocol ? (
              Object.entries(stats.by_protocol).map(([protocol, count]) => {
                const pct = stats.total > 0 ? Math.round((count as number) / stats.total * 100) : 0;
                return (
                  <div key={protocol} style={{ marginBottom: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <Text>{protocol}</Text>
                      <Text strong>{(count as number)}</Text>
                    </div>
                    <Progress percent={pct} size="small" showInfo={false} strokeColor="#4285f4" />
                  </div>
                );
              })
            ) : <Empty description="暂无数据" />}
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" title={<span><SettingOutlined /> 系统概览</span>}>
            <Row gutter={[16, 16]}>
              <Col span={12}>
                <Statistic title="解析器配置" value={data?.parser_count || 0} prefix={<FileTextOutlined />} valueStyle={{ fontSize: 20 }} />
              </Col>
              <Col span={12}>
                <Statistic title="协议类型" value={data?.protocol_count || 0} prefix={<ThunderboltOutlined />} valueStyle={{ fontSize: 20 }} />
              </Col>
            </Row>
            <div style={{ marginTop: 12 }}>
              <Text type="secondary">最后更新: {data?.timestamp ? new Date(data.timestamp).toLocaleString('zh-CN') : '-'}</Text>
            </div>
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" title={<span><SyncOutlined /> 连接健康度</span>}>
            <div style={{ textAlign: 'center', padding: '8px 0' }}>
              <Progress
                type="dashboard"
                percent={stats && stats.total > 0 ? Math.round((stats.connected / stats.total) * 100) : 0}
                size={120}
                strokeColor={{
                  '0%': '#108ee9',
                  '100%': '#34a853',
                }}
              />
              <div style={{ marginTop: 8 }}>
                <Text>连接成功率</Text>
              </div>
            </div>
          </Card>
        </Col>
      </Row>

      {/* 最近连接记录 */}
      <Card
        title={<span><SyncOutlined /> 最近连接活动</span>}
        extra={
          <Space size="middle">
            <Space size="small">
              <Switch
                size="small"
                checked={autoRefresh}
                onChange={setAutoRefresh}
                aria-label="自动刷新"
              />
              <Text type="secondary">{autoRefresh ? `自动刷新中（${REFRESH_INTERVAL / 1000}s）` : '已暂停'}</Text>
            </Space>
            <ReloadOutlined onClick={fetchData} style={{ cursor: 'pointer' }} />
          </Space>
        }
      >
        <Table
          dataSource={data?.recent_connections || []}
          columns={recentColumns}
          rowKey="id"
          pagination={false}
          size="small"
          locale={{ emptyText: <Empty description="暂无连接记录" /> }}
        />
      </Card>
    </div>
  );
};

export default ConnectionDashboard;