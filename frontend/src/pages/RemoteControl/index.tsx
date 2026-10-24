/**
 * 远程控制页面
 */
import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Button, Space, Tag, Select, message, Modal, Descriptions, Switch, Slider, Divider, Spin } from 'antd';
import { 
  PoweroffOutlined, SyncOutlined, SoundOutlined, SettingOutlined,
  PlayCircleOutlined, PauseCircleOutlined, ReloadOutlined
} from '@ant-design/icons';
import { deviceAPI, remoteAPI } from '../../api';

const { Option } = Select;

const RemoteControlPage: React.FC = () => {
  const [selectedDevice, setSelectedDevice] = useState<string>('');
  const [loading, setLoading] = useState<string | null>(null);
  const [devicesLoading, setDevicesLoading] = useState(false);
  const [powerLimit, setPowerLimit] = useState(100);
  const [devices, setDevices] = useState<any[]>([]);

  // 加载设备列表
  useEffect(() => {
    loadDevices();
  }, []);

  const loadDevices = async () => {
    setDevicesLoading(true);
    try {
      const { data } = await deviceAPI.list();
      const deviceList = Array.isArray(data) ? data : data.items || [];
      setDevices(deviceList);
      if (deviceList.length > 0) {
        setSelectedDevice(String(deviceList[0].id));
      }
    } catch (err) {
      message.error('加载设备列表失败');
    } finally {
      setDevicesLoading(false);
    }
  };

  const handleControl = async (command: string) => {
    if (!selectedDevice) {
      message.warning('请先选择设备');
      return;
    }
    setLoading(command);
    try {
      await remoteAPI.control(Number(selectedDevice), { action: command });
      message.success(`执行成功: ${command}`);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '控制失败，请稍后重试');
    } finally {
      setLoading(null);
    }
  };

  const device = devices.find(d => String(d.id) === selectedDevice);

  const controlItems = [
    { key: 'start', icon: <PlayCircleOutlined />, label: '启动', color: '#34a853', commands: ['启动设备', '自检'] },
    { key: 'stop', icon: <PauseCircleOutlined />, label: '停止', color: '#ea4335', commands: ['停止设备', '紧急停止'] },
    { key: 'restart', icon: <ReloadOutlined />, label: '重启', color: '#ff5a36', commands: ['重启设备', '恢复出厂'] },
    { key: 'setting', icon: <SettingOutlined />, label: '参数设置', color: '#722ed1', commands: ['功率设置', '模式切换'] },
  ];

  return (
    <div>
      <Row gutter={16}>
        <Col xs={24} lg={6}>
          <Card title="选择设备">
            <Select
              style={{ width: '100%' }}
              value={selectedDevice}
              onChange={setSelectedDevice}
              loading={devicesLoading}
              placeholder="请选择设备"
            >
              {devices.map(d => (
                <Option key={d.id} value={String(d.id)}>
                  <Space>
                    <Tag color={d.status === 'online' ? 'green' : 'red'}>
                      {d.status === 'online' ? '在线' : '离线'}
                    </Tag>
                    {d.name}
                  </Space>
                </Option>
              ))}
            </Select>
            
            {device && (
              <div style={{ marginTop: 16 }}>
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="设备类型">{device.type}</Descriptions.Item>
                  <Descriptions.Item label="当前功率">{device.power || 0} kW</Descriptions.Item>
                  <Descriptions.Item label="状态">
                    <Tag color={device.status === 'online' ? 'green' : 'red'}>
                      {device.status === 'online' ? '正常运行' : '离线'}
                    </Tag>
                  </Descriptions.Item>
                </Descriptions>
              </div>
            )}
          </Card>

          <Card title="快速操作" style={{ marginTop: 16 }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Button 
                block 
                icon={<PoweroffOutlined />} 
                onClick={() => handleControl('power_on')}
                loading={loading === 'power_on'}
              >
                开机
              </Button>
              <Button 
                block 
                danger 
                icon={<PoweroffOutlined />} 
                onClick={() => handleControl('power_off')}
                loading={loading === 'power_off'}
              >
                关机
              </Button>
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={18}>
          <Card title="控制面板">
            <Row gutter={[16, 16]}>
              {controlItems.map(item => (
                <Col xs={12} sm={6} key={item.key}>
                  <Card 
                    hoverable
                    style={{ textAlign: 'center', borderColor: item.color }}
                    onClick={() => handleControl(item.key)}
                  >
                    <div style={{ fontSize: 32, color: item.color }}>
                      {item.icon}
                    </div>
                    <div style={{ marginTop: 8, fontWeight: 500 }}>{item.label}</div>
                  </Card>
                </Col>
              ))}
            </Row>

            <Divider>功率限制设置</Divider>
            
            <div style={{ padding: '0 100px' }}>
              <Slider
                min={0}
                max={100}
                value={powerLimit}
                onChange={setPowerLimit}
                tooltip={{ formatter: (val) => `${val}%` }}
              />
              <div style={{ textAlign: 'center', marginTop: 8 }}>
                功率限制: <span style={{ fontSize: 20, color: '#ff5a36' }}>{powerLimit}%</span>
                <Button type="link" onClick={() => message.success('设置已保存')}>
                  应用
                </Button>
              </div>
            </div>

            <Divider>定时任务</Divider>
            
            <Row gutter={16}>
              <Col span={8}>
                <Card size="small">
                  <div style={{ textAlign: 'center' }}>
                    <div>定时开机</div>
                    <Tag color="blue">06:00</Tag>
                    <Switch checked={true} size="small" />
                  </div>
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small">
                  <div style={{ textAlign: 'center' }}>
                    <div>定时关机</div>
                    <Tag color="orange">22:00</Tag>
                    <Switch checked={true} size="small" />
                  </div>
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small">
                  <div style={{ textAlign: 'center' }}>
                    <div>峰谷调节</div>
                    <Switch checked={true} size="small" />
                  </div>
                </Card>
              </Col>
            </Row>
          </Card>

          <Card title="控制日志" style={{ marginTop: 16 }}>
            <div style={{ maxHeight: 200, overflow: 'auto' }}>
              {[
                { time: '2026-03-27 10:30:00', action: '开机', user: 'admin', result: '成功' },
                { time: '2026-03-27 10:25:00', action: '参数调整', user: 'admin', result: '成功' },
                { time: '2026-03-27 09:15:00', action: '重启', user: 'admin', result: '成功' },
              ].map((log, i) => (
                <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                  <Space>
                    <span style={{ color: '#a6a1a0' }}>{log.time}</span>
                    <Tag>{log.action}</Tag>
                    <span>{log.user}</span>
                    <Tag color="green">{log.result}</Tag>
                  </Space>
                </div>
              ))}
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default RemoteControlPage;