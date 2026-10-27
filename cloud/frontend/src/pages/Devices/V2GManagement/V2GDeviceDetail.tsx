/**
 * V2GDeviceDetail - V2G设备详情与调度控制面板
 * 
 * 展示V2G设备的运行状态、效率数据和调度控制界面
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Row, Col, Statistic, Descriptions, Tag, Badge, Button,
  Space, Slider, InputNumber, Select, Table, message, Spin, Alert, Divider,
} from 'antd';
import {
  ThunderboltOutlined, ArrowUpOutlined, ArrowDownOutlined,
  PauseCircleOutlined, SendOutlined, HistoryOutlined,
  ArrowLeftOutlined, ReloadOutlined, DashboardOutlined,
} from '@ant-design/icons';
import { deviceAPI, v2gAPI, efficiencyAPI } from '../../../api';
import type { V2GDevice, V2GDispatchRecord, DeviceEfficiency } from '../../../types';
import PageWrapper from '../../../components/PageWrapper';

const { Option } = Select;

const V2GDeviceDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const deviceId = Number(id);

  const [device, setDevice] = useState<V2GDevice | null>(null);
  const [efficiency, setEfficiency] = useState<DeviceEfficiency | null>(null);
  const [dispatchHistory, setDispatchHistory] = useState<V2GDispatchRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [dispatching, setDispatching] = useState(false);

  // 调度表单状态
  const [dispatchType, setDispatchType] = useState<string>('standby');
  const [targetPower, setTargetPower] = useState<number>(30);

  const fetchDevice = useCallback(async () => {
    if (!deviceId) return;
    setLoading(true);
    try {
      const response = await deviceAPI.get(deviceId);
      setDevice(response.data as unknown as V2GDevice);
    } catch (error: unknown) {
      message.error('获取设备信息失败');
    } finally {
      setLoading(false);
    }
  }, [deviceId]);

  const fetchEfficiency = useCallback(async () => {
    if (!deviceId) return;
    try {
      const response = await efficiencyAPI.deviceEfficiency(deviceId);
      setEfficiency(response.data as DeviceEfficiency);
    } catch {
      // 静默处理：效率数据加载失败保留上次值
    }
  }, [deviceId]);

  const fetchHistory = useCallback(async () => {
    if (!deviceId) return;
    setHistoryLoading(true);
    try {
      const response = await v2gAPI.dispatchHistory(deviceId);
      const data = response.data as { items?: V2GDispatchRecord[]; data?: V2GDispatchRecord[] };
      setDispatchHistory(data.items || data.data || []);
    } catch {
      // 静默处理 - API可能尚未部署
      setDispatchHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, [deviceId]);

  useEffect(() => {
    fetchDevice();
    fetchEfficiency();
    fetchHistory();
  }, [fetchDevice, fetchEfficiency, fetchHistory]);

  const handleDispatch = async () => {
    if (!deviceId) return;
    setDispatching(true);
    try {
      await v2gAPI.dispatch(deviceId, {
        dispatch_type: dispatchType,
        target_power_kw: targetPower,
      });
      message.success(`调度指令已下发: ${modeLabel(dispatchType)}, 目标功率 ${targetPower} kW`);
      // 刷新数据
      fetchDevice();
      fetchHistory();
    } catch (error: unknown) {
      const errMsg = (error as any)?.response?.data?.detail || (error as any)?.message || '调度失败';
      message.error('调度下发失败: ' + errMsg);
    } finally {
      setDispatching(false);
    }
  };

  const modeLabel = (mode: string): string => {
    const map: Record<string, string> = {
      charge: '充电模式',
      discharge: '放电模式',
      standby: '待机模式',
    };
    return map[mode] || mode;
  };

  const currentModeConfig: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
    charging: { label: '充电中', color: 'green', icon: <ArrowDownOutlined /> },
    discharging: { label: '放电中', color: 'red', icon: <ArrowUpOutlined /> },
    standby: { label: '待机', color: 'gold', icon: <PauseCircleOutlined /> },
  };

  const statusBadgeMap: Record<string, 'success' | 'error' | 'warning' | 'processing'> = {
    success: 'success',
    failed: 'error',
    pending: 'processing',
  };

  const historyColumns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '调度类型',
      dataIndex: 'dispatch_type',
      key: 'dispatch_type',
      width: 100,
      render: (type: string) => {
        const map: Record<string, { label: string; color: string }> = {
          charge: { label: '充电', color: 'green' },
          discharge: { label: '放电', color: 'red' },
          standby: { label: '待机', color: 'gold' },
        };
        const info = map[type];
        return info ? <Tag color={info.color}>{info.label}</Tag> : <Tag>{type}</Tag>;
      },
    },
    {
      title: '设定功率',
      dataIndex: 'target_power_kw',
      key: 'target_power_kw',
      width: 100,
      render: (val: number) => val != null ? `${val.toFixed(1)} kW` : '-',
    },
    {
      title: '实际功率',
      dataIndex: 'actual_power_kw',
      key: 'actual_power_kw',
      width: 100,
      render: (val: number) => val != null ? `${val.toFixed(1)} kW` : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => (
        <Badge
          status={statusBadgeMap[status] || 'default'}
          text={status === 'success' ? '成功' : status === 'failed' ? '失败' : status === 'pending' ? '执行中' : status}
        />
      ),
    },
    {
      title: '信息',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
      render: (m: string) => m || '-',
    },
  ];

  const isV2G = device?.type === 'v2g_charger' || device?.type === 'V2G_CHARGER';
  const hasDevice = !!device && !loading;

  return (
    <PageWrapper
      loading={loading}
      skeletonType="card"
      skeletonCount={4}
      hasData={hasDevice || !loading}
      empty={{
        type: 'device',
        title: '设备不存在',
        description: '未找到对应的V2G设备',
      }}
      transition="slide-up"
    >
      <div className="page-container">
        {/* 上下文注入数据标记 - 隐藏 */}
        {device && (
          <div
            data-context-json={JSON.stringify({
              device: {
                id: device.id,
                name: device.name,
                sn: device.sn,
                type: device.type,
                status: device.status,
                health_score: device.health_score,
                station_id: device.station_id,
              },
              v2g_device: {
                id: device.id,
                name: device.name,
                v2g_mode: (device as any).v2g_mode,
                grid_status: (device as any).grid_status,
                charge_power_kw: (device as any).charge_power_kw,
                discharge_power_kw: (device as any).discharge_power_kw,
                soc: (device as any).soc,
                power_rating_kw: (device as any).power_rating_kw,
              },
            })}
            data-device-id={String(device.id)}
            data-device-name={device.name || ''}
            data-device-sn={device.sn || ''}
            data-device-type={device.type || ''}
            data-device-status={device.status || ''}
            data-device-health={String(device.health_score || 0)}
            data-v2g-device-id={String(device.id)}
            style={{ display: 'none' }}
          />
        )}

        {/* 返回按钮 */}
        <div style={{ marginBottom: 16 }}>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/devices/v2g')}
            style={{ marginRight: 8 }}
          >
            返回V2G列表
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => { fetchDevice(); fetchEfficiency(); fetchHistory(); }}
          >
            刷新
          </Button>
        </div>

        {device && !isV2G && (
          <Alert
            type="warning"
            message="非V2G设备"
            description={`当前设备类型为 ${device.type}，V2G调度功能仅适用于V2G充电桩。`}
            style={{ marginBottom: 16 }}
            showIcon
          />
        )}

        {/* 设备基本信息 */}
        <Card
          title={
            <Space>
              <ThunderboltOutlined style={{ color: '#722ed1' }} />
              <span>设备详情 - {device?.name || '加载中...'}</span>
            </Space>
          }
          style={{ marginBottom: 16 }}
        >
          <Descriptions column={3} size="small" bordered>
            <Descriptions.Item label="设备ID">{device?.id}</Descriptions.Item>
            <Descriptions.Item label="SN码">{device?.sn}</Descriptions.Item>
            <Descriptions.Item label="设备类型">
              <Tag color="purple">V2G充电桩</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="所属站点">{device?.station_name || '-'}</Descriptions.Item>
            <Descriptions.Item label="设备状态">
              <Tag color={device?.status === 'ONLINE' ? 'green' : 'red'}>
                {device?.status === 'ONLINE' ? '在线' : device?.status === 'OFFLINE' ? '离线' : device?.status}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="健康度">
              <span style={{
                fontWeight: 'bold',
                color: (device?.health_score || 0) >= 80 ? '#34a853' : (device?.health_score || 0) >= 50 ? '#f5a623' : '#ea4335',
              }}>
                {device?.health_score || 0}%
              </span>
            </Descriptions.Item>
          </Descriptions>
        </Card>

        {/* V2G运行状态区 */}
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={24} sm={12} md={6}>
            <Card size="small">
              <Statistic
                title="当前模式"
                value={device ? currentModeConfig[device.current_mode]?.label || device.current_mode : '-'}
                prefix={device ? currentModeConfig[device.current_mode]?.icon : null}
                valueStyle={{ color: device ? currentModeConfig[device.current_mode]?.color : undefined }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card size="small">
              <Statistic
                title="实时充电功率"
                value={device?.charge_power_kw ?? '-'}
                suffix={device?.charge_power_kw != null ? 'kW' : ''}
                precision={1}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card size="small">
              <Statistic
                title="实时放电功率"
                value={device?.discharge_power_kw ?? '-'}
                suffix={device?.discharge_power_kw != null ? 'kW' : ''}
                precision={1}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card size="small">
              <Statistic
                title="额定功率"
                value={device?.rated_power_kw ?? '-'}
                suffix={device?.rated_power_kw != null ? 'kW' : ''}
                precision={1}
              />
            </Card>
          </Col>
        </Row>

        {/* 效率数据 */}
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={24} sm={8}>
            <Card size="small">
              <Statistic
                title="充电效率"
                value={efficiency?.charge_efficiency ?? device?.charge_efficiency ?? '-'}
                suffix="%"
                precision={1}
                valueStyle={{
                  color: (efficiency?.charge_efficiency || 0) >= 90 ? '#34a853' : '#f5a623',
                }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={8}>
            <Card size="small">
              <Statistic
                title="放电效率"
                value={efficiency?.discharge_efficiency ?? device?.discharge_efficiency ?? '-'}
                suffix="%"
                precision={1}
                valueStyle={{
                  color: (efficiency?.discharge_efficiency || 0) >= 90 ? '#34a853' : '#f5a623',
                }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={8}>
            <Card size="small">
              <Statistic
                title="转换效率 (AC-DC-AC)"
                value={efficiency?.conversion_efficiency ?? device?.conversion_efficiency ?? '-'}
                suffix="%"
                precision={1}
                valueStyle={{
                  color: (efficiency?.conversion_efficiency || 0) >= 85 ? '#34a853' : '#f5a623',
                }}
              />
            </Card>
          </Col>
        </Row>

        {/* V2G调度控制面板 */}
        {isV2G && (
          <Card
            title={
              <Space>
                <DashboardOutlined />
                <span>V2G调度控制</span>
              </Space>
            }
            style={{ marginBottom: 16 }}
          >
            <Row gutter={[24, 16]}>
              <Col xs={24} md={8}>
                <div style={{ marginBottom: 12 }}>
                  <div style={{ marginBottom: 8, fontWeight: 500 }}>调度模式</div>
                  <Select
                    value={dispatchType}
                    onChange={setDispatchType}
                    style={{ width: '100%' }}
                  >
                    <Option value="charge">
                      <Space>
                        <ArrowDownOutlined style={{ color: '#34a853' }} />
                        充电模式
                      </Space>
                    </Option>
                    <Option value="discharge">
                      <Space>
                        <ArrowUpOutlined style={{ color: '#ea4335' }} />
                        放电模式
                      </Space>
                    </Option>
                    <Option value="standby">
                      <Space>
                        <PauseCircleOutlined style={{ color: '#f5a623' }} />
                        待机模式
                      </Space>
                    </Option>
                  </Select>
                </div>
              </Col>
              <Col xs={24} md={10}>
                <div style={{ marginBottom: 12 }}>
                  <div style={{ marginBottom: 8, fontWeight: 500 }}>目标功率 (kW)</div>
                  <Row gutter={8} align="middle">
                    <Col flex="auto">
                      <Slider
                        min={0}
                        max={device?.rated_power_kw || 200}
                        step={0.5}
                        value={targetPower}
                        onChange={setTargetPower}
                        marks={{
                          0: '0',
                          [(device?.rated_power_kw || 200) / 2]: `${((device?.rated_power_kw || 200) / 2)}`,
                          [device?.rated_power_kw || 200]: `${device?.rated_power_kw || 200}`,
                        }}
                      />
                    </Col>
                    <Col>
                      <InputNumber
                        min={0}
                        max={device?.rated_power_kw || 200}
                        step={0.5}
                        value={targetPower}
                        onChange={(v) => setTargetPower(v || 0)}
                        style={{ width: 80 }}
                        addonAfter="kW"
                      />
                    </Col>
                  </Row>
                </div>
              </Col>
              <Col xs={24} md={6}>
                <div style={{ display: 'flex', flexDirection: 'column', height: '100%', justifyContent: 'flex-end' }}>
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    loading={dispatching}
                    onClick={handleDispatch}
                    block
                    size="large"
                    style={{
                      background: dispatchType === 'discharge' ? '#ea4335' : dispatchType === 'charge' ? '#34a853' : undefined,
                      borderColor: dispatchType === 'discharge' ? '#ea4335' : dispatchType === 'charge' ? '#34a853' : undefined,
                    }}
                  >
                    下发调度指令
                  </Button>
                </div>
              </Col>
            </Row>
          </Card>
        )}

        {/* 调度历史记录 */}
        <Card
          title={
            <Space>
              <HistoryOutlined />
              <span>调度历史</span>
            </Space>
          }
          extra={
            <Button size="small" onClick={fetchHistory} loading={historyLoading}>
              刷新
            </Button>
          }
        >
          <div className="table-scroll-x">
            <Table
              columns={historyColumns}
              dataSource={dispatchHistory}
              rowKey="id"
              loading={historyLoading}
              size="small"
              pagination={{ pageSize: 10, size: 'small' }}
              locale={{ emptyText: '暂无调度记录' }}
            />
          </div>
        </Card>
      </div>
    </PageWrapper>
  );
};

export default V2GDeviceDetail;