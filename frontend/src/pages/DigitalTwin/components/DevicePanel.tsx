import React from 'react';
import { Card, List, Tag, Button, Space, Statistic, Tooltip } from 'antd';
import {
  ThunderboltOutlined,
  BulbOutlined,
  PoweroffOutlined,
  DashboardOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  SyncOutlined
} from '@ant-design/icons';

interface DevicePanelProps {
  devices: any[];
  selectedDeviceId: number | null;
  onSelectDevice: (deviceId: number) => void;
  realtimeData: any;
}

const DevicePanel: React.FC<DevicePanelProps> = ({
  devices,
  selectedDeviceId,
  onSelectDevice,
  realtimeData
}) => {
  // 获取设备状态标签颜色
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'online':
        return 'green';
      case 'warning':
      case 'alarm':
        return 'gold';
      case 'fault':
        return 'red';
      case 'charging':
        return 'orange';
      case 'offline':
        return 'default';
      default:
        return 'blue';
    }
  };

  // 获取设备状态图标
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'online':
        return <CheckCircleOutlined style={{ color: '#34a853' }} />;
      case 'warning':
      case 'alarm':
        return <ExclamationCircleOutlined style={{ color: '#f5a623' }} />;
      case 'fault':
        return <ExclamationCircleOutlined style={{ color: '#ea4335' }} />;
      case 'charging':
        return <SyncOutlined spin style={{ color: '#fa8c16' }} />;
      case 'offline':
        return <PoweroffOutlined style={{ color: '#a6a1a0' }} />;
      default:
        return <DashboardOutlined style={{ color: '#ff5a36' }} />;
    }
  };

  // 获取设备类型图标
  const getDeviceIcon = (type: string) => {
    switch (type) {
      case 'inverter':
        return <ThunderboltOutlined style={{ color: '#ff5a36' }} />;
      case 'pv_panel':
        return <BulbOutlined style={{ color: '#f5a623' }} />;
      case 'battery':
        return <PoweroffOutlined style={{ color: '#34a853' }} />;
      case 'charger':
        return <ThunderboltOutlined style={{ color: '#722ed1' }} />;
      default:
        return <DashboardOutlined style={{ color: '#666' }} />;
    }
  };

  // 获取实时数据
  const getRealtimeData = (deviceId: number) => {
    if (!realtimeData?.devices) return null;
    return realtimeData.devices[deviceId];
  };

  // 计算设备健康度颜色
  const getHealthColor = (healthScore: number) => {
    if (healthScore >= 90) return '#3f8600';
    if (healthScore >= 70) return '#f5a623';
    if (healthScore >= 50) return '#fa8c16';
    return '#cf1322';
  };

  // 格式化数值
  const formatValue = (value: number | null, unit: string) => {
    if (value === null || value === undefined) return '-';
    return `${value.toFixed(2)} ${unit}`;
  };

  return (
    <div>
      {/* 设备统计概览 */}
      <Card
        title="设备统计"
        size="small"
        style={{ marginBottom: 16 }}
      >
        <Space size="large" style={{ width: '100%', justifyContent: 'space-around' }}>
          <Statistic
            title="总设备数"
            value={devices.length}
            prefix={<DashboardOutlined />}
          />
          <Statistic
            title="在线设备"
            value={devices.filter(d => d.device.status === 'online').length}
            valueStyle={{ color: '#34a853' }}
          />
          <Statistic
            title="故障设备"
            value={devices.filter(d => d.device.status === 'fault').length}
            valueStyle={{ color: '#ea4335' }}
          />
        </Space>
      </Card>

      {/* 设备列表 */}
      <Card title="设备列表" size="small">
        <List
          dataSource={devices}
          renderItem={(item) => {
            const device = item.device;
            const isSelected = device.id === selectedDeviceId;
            const rtData = getRealtimeData(device.id);

            return (
              <List.Item
                className={`device-card ${isSelected ? 'selected' : ''}`}
                onClick={() => onSelectDevice(device.id)}
                style={{
                  border: isSelected ? '2px solid #ff5a36' : '1px solid #f0f0f0',
                  borderRadius: '6px',
                  marginBottom: '8px',
                  padding: '12px',
                  cursor: 'pointer',
                  transition: 'all 0.3s'
                }}
              >
                <div style={{ width: '100%' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                      <Tooltip title={device.type}>
                        {getDeviceIcon(device.type)}
                      </Tooltip>
                      <div style={{ marginLeft: 8 }}>
                        <strong>{device.name}</strong>
                        <div style={{ fontSize: '12px', color: '#666' }}>
                          {device.model || '未指定型号'} | {device.location || '未设置位置'}
                        </div>
                      </div>
                    </div>
                    <div>
                      <Tag 
                        icon={getStatusIcon(device.status)}
                        color={getStatusColor(device.status)}
                      >
                        {device.status === 'online' ? '在线' :
                         device.status === 'warning' || device.status === 'alarm' ? '告警' :
                         device.status === 'fault' ? '故障' :
                         device.status === 'charging' ? '充电中' : '离线'}
                      </Tag>
                    </div>
                  </div>

                  <div style={{ marginTop: 8 }}>
                    {/* 健康度 */}
                    <div style={{ display: 'flex', alignItems: 'center', marginBottom: 4 }}>
                      <div style={{ width: 60, fontSize: '12px', color: '#666' }}>健康度:</div>
                      <Tooltip title={`${device.health_score || 0}%`}>
                        <div style={{ flex: 1 }}>
                          <div
                            style={{
                              height: '8px',
                              background: getHealthColor(device.health_score || 0),
                              borderRadius: '4px',
                              width: `${device.health_score || 0}%`
                            }}
                          />
                        </div>
                      </Tooltip>
                      <div style={{ marginLeft: 8, fontSize: '12px', fontWeight: 'bold' }}>
                        {device.health_score || 0}%
                      </div>
                    </div>

                    {/* 实时数据 */}
                    {rtData && (
                      <div style={{ 
                        marginTop: 8, 
                        padding: '8px',
                        background: '#f6ffed',
                        borderRadius: '4px',
                        fontSize: '12px'
                      }}>
                        <div style={{ fontWeight: 'bold', marginBottom: 4 }}>实时数据:</div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span>
                            功率: <strong>{formatValue(rtData.power_kw, 'kW')}</strong>
                          </span>
                          <span>
                            电压: <strong>{formatValue(rtData.voltage_v, 'V')}</strong>
                          </span>
                          <span>
                            电流: <strong>{formatValue(rtData.current_a, 'A')}</strong>
                          </span>
                        </div>
                        <div style={{ marginTop: 4 }}>
                          温度: <strong>{formatValue(rtData.temperature_c, '°C')}</strong> | 
                          频率: <strong>{formatValue(rtData.frequency_hz, 'Hz')}</strong>
                        </div>
                      </div>
                    )}

                    {/* 累计数据 */}
                    <div style={{ marginTop: 8, fontSize: '12px' }}>
                      <span style={{ marginRight: 16 }}>
                        发电: <strong>{formatValue(device.total_generation_kwh, 'kWh')}</strong>
                      </span>
                      <span>
                        运行: <strong>{device.total_run_hours || 0}h</strong>
                      </span>
                    </div>

                    {/* 最后心跳 */}
                    <div style={{ marginTop: 4, fontSize: '12px', color: '#999' }}>
                      最后心跳: {device.last_heartbeat ? 
                        new Date(device.last_heartbeat).toLocaleString() : 
                        '从未'}
                    </div>
                  </div>

                  {/* 操作按钮 */}
                  <div style={{ marginTop: 8, textAlign: 'right' }}>
                    <Space size="small">
                      <Button size="small" onClick={() => onSelectDevice(device.id)}>
                        查看详情
                      </Button>
                      {device.status === 'fault' && (
                        <Button size="small" type="primary" danger>
                          修复
                        </Button>
                      )}
                    </Space>
                  </div>
                </div>
              </List.Item>
            );
          }}
        />
      </Card>

      {/* 快速筛选 */}
      <Card
        title="快速筛选"
        size="small"
        style={{ marginTop: 16 }}
      >
        <Space wrap>
          <Button 
            size="small" 
            onClick={() => {
              const onlineDevice = devices.find(d => d.device.status === 'online');
              if (onlineDevice) onSelectDevice(onlineDevice.device.id);
            }}
          >
            在线设备
          </Button>
          <Button 
            size="small" 
            danger
            onClick={() => {
              const faultDevice = devices.find(d => d.device.status === 'fault');
              if (faultDevice) onSelectDevice(faultDevice.device.id);
            }}
          >
            故障设备
          </Button>
          <Button 
            size="small" 
            type="primary"
            onClick={() => {
              const chargingDevice = devices.find(d => d.device.status === 'charging');
              if (chargingDevice) onSelectDevice(chargingDevice.device.id);
            }}
          >
            充电中
          </Button>
          <Button 
            size="small"
            onClick={() => {
              // 选中第一个设备
              if (devices.length > 0) {
                onSelectDevice(devices[0].device.id);
              }
            }}
          >
            第一个设备
          </Button>
        </Space>
      </Card>
    </div>
  );
};

export default DevicePanel;