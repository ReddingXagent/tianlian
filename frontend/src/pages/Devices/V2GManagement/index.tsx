/**
 * V2G设备管理页面 - V2G设备总览、调度控制
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Button, Space, Tag, Statistic, Row, Col, message, Spin,
} from 'antd';
import {
  ReloadOutlined, ThunderboltOutlined,
  ArrowUpOutlined, ArrowDownOutlined, PauseCircleOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { deviceAPI } from '../../../api';
import type { PaginatedData } from '../../../types';
import type { V2GDevice, V2GOverview } from '../../../types';
import PageWrapper from '../../../components/PageWrapper';

const V2GManagementPage: React.FC = () => {
  const navigate = useNavigate();
  const [devices, setDevices] = useState<V2GDevice[]>([]);
  const [loading, setLoading] = useState(false);
  const [overview, setOverview] = useState<V2GOverview>({
    total: 0, charging_count: 0, discharging_count: 0, standby_count: 0,
    today_charge_kwh: 0, today_discharge_kwh: 0,
  });
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const fetchDevices = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {
        type: 'v2g_charger',
        page,
        page_size: pageSize,
      };
      const response = await deviceAPI.list(params);
      const respData = response.data as unknown as PaginatedData<V2GDevice>;
      const items = respData.items || [];
      setDevices(items);
      setTotal(respData.total || 0);

      // 计算概览数据
      const ov: V2GOverview = {
        total: items.length,
        charging_count: items.filter(d => d.current_mode === 'charging').length,
        discharging_count: items.filter(d => d.current_mode === 'discharging').length,
        standby_count: items.filter(d => d.current_mode === 'standby').length,
        today_charge_kwh: items.reduce((sum, d) => sum + (d.charge_power_kw || 0), 0),
        today_discharge_kwh: items.reduce((sum, d) => sum + (d.discharge_power_kw || 0), 0),
      };
      setOverview(ov);
    } catch (error: unknown) {
      message.error('获取V2G设备列表失败: ' + ((error as any)?.response?.data?.detail || (error as any)?.message));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => {
    fetchDevices();
  }, [fetchDevices]);

  const modeConfig: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
    charging: { label: '充电中', color: 'green', icon: <ArrowDownOutlined /> },
    discharging: { label: '放电中', color: 'red', icon: <ArrowUpOutlined /> },
    standby: { label: '待机', color: 'gold', icon: <PauseCircleOutlined /> },
  };

  const statusColorMap: Record<string, string> = {
    online: 'green', ONLINE: 'green',
    offline: 'red', OFFLINE: 'red',
    charging: 'blue', CHARGING: 'blue',
    fault: 'orange', FAULT: 'orange',
    maintenance: 'gold', MAINTENANCE: 'gold',
  };

  const columns = [
    {
      title: '设备名称',
      dataIndex: 'name',
      key: 'name',
      width: 160,
      render: (text: string, record: V2GDevice) => (
        <a onClick={() => navigate(`/devices/v2g/${record.id}`)} style={{ cursor: 'pointer' }}>
          <ThunderboltOutlined style={{ marginRight: 6, color: '#722ed1' }} />
          {text}
        </a>
      ),
    },
    {
      title: '所属站点',
      dataIndex: 'station_name',
      key: 'station_name',
      width: 120,
      render: (text: string) => text || '-',
    },
    {
      title: '当前模式',
      dataIndex: 'current_mode',
      key: 'current_mode',
      width: 110,
      render: (mode: string) => {
        const cfg = modeConfig[mode];
        return cfg ? (
          <Tag color={cfg.color} icon={cfg.icon}>{cfg.label}</Tag>
        ) : <Tag>{mode || '未知'}</Tag>;
      },
    },
    {
      title: '充电功率',
      dataIndex: 'charge_power_kw',
      key: 'charge_power_kw',
      width: 100,
      render: (val: number) => val != null ? `${val.toFixed(1)} kW` : '-',
    },
    {
      title: '放电功率',
      dataIndex: 'discharge_power_kw',
      key: 'discharge_power_kw',
      width: 100,
      render: (val: number) => val != null ? `${val.toFixed(1)} kW` : '-',
    },
    {
      title: '充电效率',
      dataIndex: 'charge_efficiency',
      key: 'charge_efficiency',
      width: 100,
      render: (val: number) => {
        if (val == null) return '-';
        return (
          <span style={{ color: val >= 90 ? '#34a853' : val >= 80 ? '#f5a623' : '#ea4335' }}>
            {val.toFixed(1)}%
          </span>
        );
      },
    },
    {
      title: '放电效率',
      dataIndex: 'discharge_efficiency',
      key: 'discharge_efficiency',
      width: 100,
      render: (val: number) => {
        if (val == null) return '-';
        return (
          <span style={{ color: val >= 90 ? '#34a853' : val >= 80 ? '#f5a623' : '#ea4335' }}>
            {val.toFixed(1)}%
          </span>
        );
      },
    },
    {
      title: '健康度',
      dataIndex: 'health_score',
      key: 'health_score',
      width: 90,
      render: (score: number) => (
        <span
          style={{
            fontWeight: 'bold',
            color: score >= 80 ? '#34a853' : score >= 50 ? '#f5a623' : '#ea4335',
          }}
        >
          {score || 0}%
        </span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => (
        <Tag color={statusColorMap[status] || 'default'}>
          {status === 'ONLINE' ? '在线' : status === 'OFFLINE' ? '离线' : status}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: unknown, record: V2GDevice) => (
        <Button
          type="link"
          size="small"
          onClick={() => navigate(`/devices/v2g/${record.id}`)}
        >
          调度详情
        </Button>
      ),
    },
  ];

  const hasDevices = devices.length > 0 || !loading;

  return (
    <PageWrapper
      loading={loading && devices.length === 0}
      skeletonType="card"
      skeletonCount={4}
      hasData={hasDevices}
      empty={{
        type: 'device',
        title: '暂无V2G设备',
        description: '没有找到类型为 V2G 充电桩的设备',
      }}
      transition="slide-up"
    >
      <div className="page-container">
        {/* V2G概览卡片 */}
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic
                title="V2G设备总数"
                value={overview.total}
                prefix={<ThunderboltOutlined style={{ color: '#722ed1' }} />}
              />
            </Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic
                title="充电中"
                value={overview.charging_count}
                valueStyle={{ color: '#34a853' }}
                prefix={<ArrowDownOutlined />}
              />
            </Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic
                title="放电中"
                value={overview.discharging_count}
                valueStyle={{ color: '#ea4335' }}
                prefix={<ArrowUpOutlined />}
              />
            </Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic
                title="待机中"
                value={overview.standby_count}
                valueStyle={{ color: '#f5a623' }}
                prefix={<PauseCircleOutlined />}
              />
            </Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic
                title="今日充电量"
                value={overview.today_charge_kwh}
                suffix="kWh"
                precision={1}
                valueStyle={{ color: '#34a853' }}
              />
            </Card>
          </Col>
          <Col xs={12} sm={8} md={4}>
            <Card size="small">
              <Statistic
                title="今日放电量"
                value={overview.today_discharge_kwh}
                suffix="kWh"
                precision={1}
                valueStyle={{ color: '#ea4335' }}
              />
            </Card>
          </Col>
        </Row>

        {/* V2G设备列表 */}
        <Card
          title="V2G设备列表"
          extra={
            <Button icon={<ReloadOutlined />} onClick={fetchDevices}>
              刷新
            </Button>
          }
        >
          <div className="table-scroll-x">
            <Table
              columns={columns}
              dataSource={devices}
              rowKey="id"
              loading={loading}
              pagination={{
                current: page,
                pageSize: pageSize,
                total: total,
                showSizeChanger: true,
                showTotal: (t) => `共 ${t} 台V2G设备`,
                onChange: (p, ps) => {
                  setPage(p);
                  setPageSize(ps);
                },
              }}
            />
          </div>
        </Card>
      </div>
    </PageWrapper>
  );
};

export default V2GManagementPage;