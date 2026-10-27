/**
 * 天链 V3 - 告警通知中心
 * 功能: 实时告警通知列表 + 标记已读/解决/忽略 + 统计
 */
import React, { useEffect, useState, useMemo } from 'react';
import { Card, Table, Tag, Button, Space, Select, message, Badge, Row, Col, Statistic, Popconfirm, Tooltip } from 'antd';
import {
  BellOutlined, CheckCircleOutlined, DeleteOutlined,
  ReloadOutlined, ExclamationCircleOutlined, WarningOutlined,
  InfoCircleOutlined, CloseCircleOutlined, EyeOutlined
} from '@ant-design/icons';
import { alarmNoticeAPI } from '../../api';

interface NoticeItem {
  id: number;
  device_id: number;
  station_id: number | null;
  content: string;
  level: string;
  status: string;
  alarm_type: string;
  fault_code: string;
  fault_source: string;
  trigger_metric: string;
  trigger_value: number | null;
  created_at: string;
}

const LEVEL_CONFIG: Record<string, { color: string; icon: React.ReactNode; text: string }> = {
  fatal: { color: 'red', icon: <ExclamationCircleOutlined />, text: '致命' },
  critical: { color: 'red', icon: <ExclamationCircleOutlined />, text: '紧急' },
  warning: { color: 'orange', icon: <WarningOutlined />, text: '警告' },
  info: { color: 'blue', icon: <InfoCircleOutlined />, text: '提示' },
};

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  active: { color: 'red', text: '未处理' },
  acknowledged: { color: 'blue', text: '已确认' },
  processing: { color: 'processing', text: '处理中' },
  resolved: { color: 'green', text: '已解决' },
  ignored: { color: 'default', text: '已忽略' },
};

const AlarmNoticePage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<NoticeItem[]>([]);
  const [stats, setStats] = useState<any>({ total_unread: 0, critical: 0, warning: 0, info: 0 });
  const [filterLevel, setFilterLevel] = useState<string>('');
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });

  useEffect(() => {
    fetchData();
    fetchStats();
    // 每30秒刷新
    const interval = setInterval(() => { fetchData(); fetchStats(); }, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    fetchData();
  }, [filterLevel, filterStatus, pagination.current]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const params: any = { page: pagination.current, page_size: pagination.pageSize };
      if (filterLevel) params.level = filterLevel;
      if (filterStatus) params.status = filterStatus;
      
      const res: any = await alarmNoticeAPI.list(params);
      setItems(res.data?.items || []);
      setPagination(prev => ({ ...prev, total: res.data?.total || 0 }));
    } catch {
      message.error('加载告警通知失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const res: any = await alarmNoticeAPI.stats();
      setStats(res.data || { total_unread: 0 });
    } catch { /* ignore */ }
  };

  const handleMarkRead = async (id: number) => {
    try {
      await alarmNoticeAPI.markRead(id);
      message.success('已确认');
      fetchData();
      fetchStats();
    } catch {
      message.error('操作失败');
    }
  };

  const handleResolve = async (id: number) => {
    try {
      await alarmNoticeAPI.resolve(id);
      message.success('告警已解决');
      fetchData();
      fetchStats();
    } catch {
      message.error('操作失败');
    }
  };

  const handleResolveWithDesc = async (id: number, desc: string) => {
    try {
      await alarmNoticeAPI.resolve(id, desc);
      message.success('告警已解决');
      fetchData();
      fetchStats();
    } catch {
      message.error('操作失败');
    }
  };

  const handleIgnore = async (id: number) => {
    try {
      await alarmNoticeAPI.ignore(id);
      message.success('已忽略');
      fetchData();
      fetchStats();
    } catch {
      message.error('操作失败');
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await alarmNoticeAPI.markAllRead();
      message.success('全部标记已读');
      fetchData();
      fetchStats();
    } catch {
      message.error('操作失败');
    }
  };

  const columns = [
    {
      title: '级别',
      dataIndex: 'level',
      key: 'level',
      width: 80,
      render: (level: string) => {
        const cfg = LEVEL_CONFIG[level] || LEVEL_CONFIG.info;
        return <Tag color={cfg.color}>{cfg.icon} {cfg.text}</Tag>;
      },
    },
    {
      title: '告警内容',
      dataIndex: 'content',
      key: 'content',
      ellipsis: true,
      render: (text: string, record: NoticeItem) => (
        <Tooltip title={
          <div>
            <div>{text}</div>
            {record.fault_code && <div>故障码: {record.fault_code}</div>}
            {record.trigger_metric && <div>指标: {record.trigger_metric} = {record.trigger_value}</div>}
          </div>
        }>
          <span style={{ cursor: 'pointer' }}>{text}</span>
        </Tooltip>
      ),
    },
    {
      title: '设备',
      dataIndex: 'device_id',
      key: 'device_id',
      width: 80,
      render: (id: number) => <Tag>#{id}</Tag>,
    },
    {
      title: '类型',
      dataIndex: 'alarm_type',
      key: 'alarm_type',
      width: 100,
      render: (t: string) => t ? <Tag color="default">{t}</Tag> : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (s: string) => {
        const cfg = STATUS_MAP[s] || STATUS_MAP.active;
        return <Tag color={cfg.color}>{cfg.text}</Tag>;
      },
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (t: string) => t ? new Date(t).toLocaleString() : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: NoticeItem) => (
        <Space>
          {record.status === 'active' && (
            <Button size="small" icon={<EyeOutlined />} onClick={() => handleMarkRead(record.id)}>
              确认
            </Button>
          )}
          {['active', 'acknowledged'].includes(record.status) && (
            <Button size="small" type="primary" icon={<CheckCircleOutlined />}
              onClick={() => handleResolve(record.id)}>
              解决
            </Button>
          )}
          {record.status === 'active' && (
            <Popconfirm title="确定忽略此告警?" onConfirm={() => handleIgnore(record.id)}>
              <Button size="small" icon={<CloseCircleOutlined />}>忽略</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  const activeCount = items.filter(i => i.status === 'active').length;

  return (
    <div className="page-container">
      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card hoverable>
            <Statistic
              title="未处理告警"
              value={stats.total_unread}
              valueStyle={{ color: stats.total_unread > 0 ? '#cf1322' : '#3f8600' }}
              prefix={<BellOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable>
            <Statistic
              title="紧急/致命"
              value={(stats.critical || 0) + (stats.fatal || 0)}
              valueStyle={{ color: (stats.critical || 0) > 0 ? '#cf1322' : '#3f8600' }}
              prefix={<ExclamationCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable>
            <Statistic
              title="警告"
              value={stats.warning || 0}
              valueStyle={{ color: (stats.warning || 0) > 0 ? '#f5a623' : '#3f8600' }}
              prefix={<WarningOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable>
            <Statistic
              title="提示"
              value={stats.info || 0}
              valueStyle={{ color: '#ff5a36' }}
              prefix={<InfoCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title={
          <Space>
            <BellOutlined />
            <span>告警通知列表</span>
            {activeCount > 0 && <Badge count={activeCount} style={{ backgroundColor: '#cf1322' }} />}
          </Space>
        }
        extra={
          <Space>
            <Select
              placeholder="告警级别"
              allowClear
              style={{ width: 120 }}
              value={filterLevel || undefined}
              onChange={(v) => setFilterLevel(v || '')}
            >
              <Select.Option value="fatal">致命</Select.Option>
              <Select.Option value="critical">紧急</Select.Option>
              <Select.Option value="warning">警告</Select.Option>
              <Select.Option value="info">提示</Select.Option>
            </Select>
            <Select
              placeholder="状态"
              allowClear
              style={{ width: 120 }}
              value={filterStatus || undefined}
              onChange={(v) => setFilterStatus(v || '')}
            >
              <Select.Option value="active">未处理</Select.Option>
              <Select.Option value="acknowledged">已确认</Select.Option>
              <Select.Option value="resolved">已解决</Select.Option>
              <Select.Option value="ignored">已忽略</Select.Option>
            </Select>
            <Button icon={<ReloadOutlined />} onClick={() => { fetchData(); fetchStats(); }}>刷新</Button>
            <Button type="primary" icon={<CheckCircleOutlined />} onClick={handleMarkAllRead}>
              全部确认
            </Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={items}
          rowKey="id"
          loading={loading}
          pagination={{
            ...pagination,
            showTotal: (t) => `共 ${t} 条`,
            showSizeChanger: false,
            onChange: (page) => setPagination(prev => ({ ...prev, current: page })),
          }}
          scroll={{ x: 900 }}
        />
      </Card>
    </div>
  );
};

export default AlarmNoticePage;
