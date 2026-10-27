/**
 * 数字孪生可视化页面
 * Phase9 - 3D设备模型+实时数据映射
 */
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Row, Col, Button, Spin, message, Select, Tabs, Space,
  Statistic, Tag, Tooltip, Modal,
} from 'antd';
import {
  EyeOutlined, SettingOutlined, ExpandOutlined, RotateLeftOutlined,
  RotateRightOutlined, ZoomInOutlined, ZoomOutOutlined, FullscreenExitOutlined,
  InfoCircleOutlined, ReloadOutlined, PlayCircleOutlined, PauseCircleOutlined,
  ApartmentOutlined,
} from '@ant-design/icons';
import DigitalTwinCanvas from './components/DigitalTwinCanvas';
import DevicePanel from './components/DevicePanel';
import SceneSettings from './components/SceneSettings';
import { useDigitalTwin } from './hooks/useDigitalTwin';
import { stationAPI } from '../../api';
import './index.less';

const DigitalTwinPage: React.FC = () => {
  const { stationId } = useParams<{ stationId: string }>();
  const navigate = useNavigate();
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isPlaying, setIsPlaying] = useState(true);
  const [sceneScale, setSceneScale] = useState(1);
  const [viewMode, setViewMode] = useState<'overview' | 'first_person' | 'free'>('overview');

  const {
    station, scene, devices, isLoading, error,
    refreshData, updateDeviceConfig, updateSceneConfig, realtimeData,
  } = useDigitalTwin(stationId ? parseInt(stationId) : 0);

  useEffect(() => {
    if (error) message.error(`加载失败: ${error.message}`);
  }, [error]);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isPlaying && stationId) {
      interval = setInterval(() => refreshData(), 5000);
    }
    return () => clearInterval(interval);
  }, [isPlaying, refreshData, stationId]);

  const handleFullscreen = () => {
    if (!isFullscreen) {
      document.documentElement.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
    setIsFullscreen(!isFullscreen);
  };

  const selectedDevice = devices?.find(d => d.device.id === selectedDeviceId);

  // 无 stationId 时显示站点选择列表
  if (!stationId) {
    return <StationOverview onSelect={(id) => navigate(`/digital-twin/${id}`)} />;
  }

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px' }}>
        <Spin size="large" tip="加载数字孪生场景..." />
      </div>
    );
  }

  if (!station) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: '50px' }}>
          <h2>站点不存在或无法访问</h2>
          <Button type="primary" onClick={() => navigate('/digital-twin')}>
            返回站点选择
          </Button>
        </div>
      </Card>
    );
  }

  return (
    <div className="digital-twin-page">
      <Card className="page-header" bordered={false}>
        <Row justify="space-between" align="middle">
          <Col>
            <h1 style={{ margin: 0 }}>
              <EyeOutlined style={{ marginRight: 8 }} />
              {station.name} - 数字孪生可视化
            </h1>
            <div style={{ marginTop: 8, color: '#666' }}>
              {station.address} | 设备数量: {devices?.length || 0}
            </div>
          </Col>
          <Col>
            <Space>
              <Tooltip title="返回站点列表">
                <Button icon={<ApartmentOutlined />} onClick={() => navigate('/digital-twin')} />
              </Tooltip>
              <Tooltip title="刷新数据">
                <Button icon={<ReloadOutlined />} onClick={refreshData} loading={isLoading} />
              </Tooltip>
              <Tooltip title={isPlaying ? '暂停自动刷新' : '开始自动刷新'}>
                <Button
                  icon={isPlaying ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                  type={isPlaying ? 'primary' : 'default'}
                  onClick={() => setIsPlaying(!isPlaying)}
                />
              </Tooltip>
              <Select value={viewMode} onChange={setViewMode} style={{ width: 120 }}>
                <Select.Option value="overview">上帝视角</Select.Option>
                <Select.Option value="first_person">第一人称</Select.Option>
                <Select.Option value="free">自由视角</Select.Option>
              </Select>
              <Tooltip title="场景设置">
                <Button icon={<SettingOutlined />} onClick={() => setShowSettings(true)} />
              </Tooltip>
              <Tooltip title={isFullscreen ? '退出全屏' : '全屏显示'}>
                <Button
                  icon={isFullscreen ? <FullscreenExitOutlined /> : <ExpandOutlined />}
                  onClick={handleFullscreen}
                />
              </Tooltip>
            </Space>
          </Col>
        </Row>
      </Card>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={16}>
          <Card
            className="visualization-card"
            bordered={false}
            title={
              <Space>
                <span>3D可视化</span>
                <Tag color="blue">实时</Tag>
                {realtimeData && (
                  <Tag color="green">
                    最后更新: {new Date(realtimeData.timestamp).toLocaleTimeString()}
                  </Tag>
                )}
              </Space>
            }
            extra={
              <Space>
                <Tooltip title="缩小">
                  <Button size="small" icon={<ZoomOutOutlined />}
                    onClick={() => setSceneScale(Math.max(0.5, sceneScale - 0.1))} />
                </Tooltip>
                <Button size="small" onClick={() => setSceneScale(1)}>
                  {sceneScale.toFixed(1)}x
                </Button>
                <Tooltip title="放大">
                  <Button size="small" icon={<ZoomInOutlined />}
                    onClick={() => setSceneScale(Math.min(2, sceneScale + 0.1))} />
                </Tooltip>
              </Space>
            }
          >
            <div className="canvas-container" style={{ height: '600px' }}>
              <DigitalTwinCanvas
                station={station}
                scene={scene}
                devices={devices || []}
                selectedDeviceId={selectedDeviceId}
                onDeviceSelect={handleDeviceSelect}
                viewMode={viewMode}
                scale={sceneScale}
                realtimeData={realtimeData}
              />
            </div>
          </Card>
        </Col>

        <Col span={8}>
          <Tabs defaultActiveKey="devices" items={[
            {
              key: 'devices',
              label: '设备列表',
              children: (
                <DevicePanel
                  devices={devices || []}
                  selectedDeviceId={selectedDeviceId}
                  onSelectDevice={handleDeviceSelect}
                  realtimeData={realtimeData}
                />
              ),
            },
            {
              key: 'realtime',
              label: '实时数据',
              children: selectedDevice ? (
                <Card title={
                  <Space>
                    <span>{selectedDevice.device.name}</span>
                    <Tag color={
                      selectedDevice.device.status === 'online' ? 'green' :
                      selectedDevice.device.status === 'warning' || selectedDevice.device.status === 'alarm' ? 'gold' :
                      selectedDevice.device.status === 'fault' ? 'red' :
                      selectedDevice.device.status === 'charging' ? 'orange' : 'default'
                    }>
                      {selectedDevice.device.status === 'warning' || selectedDevice.device.status === 'alarm' ? '告警' : selectedDevice.device.status}
                    </Tag>
                  </Space>
                }>
                  <Row gutter={[16, 16]}>
                    <Col span={12}>
                      <Statistic title="健康度" value={selectedDevice.device.health_score} suffix="%"
                        valueStyle={{
                          color: selectedDevice.device.health_score > 80 ? '#3f8600' :
                                 selectedDevice.device.health_score > 60 ? '#f5a623' : '#cf1322',
                        }}
                      />
                    </Col>
                    <Col span={12}>
                      <Statistic title="运行时长" value={selectedDevice.device.total_run_hours || 0} suffix="小时" />
                    </Col>
                    <Col span={12}>
                      <Statistic title="发电量" value={selectedDevice.device.total_generation_kwh || 0} suffix="kWh" />
                    </Col>
                    <Col span={12}>
                      <Statistic title="充电量" value={selectedDevice.device.total_charge_kwh || 0} suffix="kWh" />
                    </Col>
                  </Row>
                  <div style={{ marginTop: 16 }}>
                    <h4>设备详情</h4>
                    <div><strong>类型:</strong> {selectedDevice.device.type}</div>
                    <div><strong>型号:</strong> {selectedDevice.device.model || '未知'}</div>
                    <div><strong>位置:</strong> {selectedDevice.device.location || '未设置'}</div>
                    <div><strong>最后心跳:</strong> {
                      selectedDevice.device.last_heartbeat
                        ? new Date(selectedDevice.device.last_heartbeat).toLocaleString()
                        : '从未'
                    }</div>
                  </div>
                </Card>
              ) : (
                <div style={{ textAlign: 'center', padding: '50px' }}>
                  <InfoCircleOutlined style={{ fontSize: 48, color: '#999' }} />
                  <div style={{ marginTop: 16, color: '#666' }}>请在左侧选择设备以查看详情</div>
                </div>
              ),
            },
            {
              key: 'scene',
              label: '场景信息',
              children: (
                <Card title="场景配置">
                  <Row gutter={16}>
                    <Col span={8}><Statistic title="设备总数" value={devices?.length || 0} /></Col>
                    <Col span={8}>
                      <Statistic title="在线设备"
                        value={devices?.filter(d => d.device.status === 'online').length || 0} />
                    </Col>
                    <Col span={8}>
                      <Statistic title="告警设备"
                        value={devices?.filter(d => d.device.status === 'warning' || d.device.status === 'alarm').length || 0}
                        valueStyle={{ color: '#f5a623' }} />
                    </Col>
                  </Row>
                  <div style={{ marginTop: 16 }}>
                    <div><strong>创建时间:</strong> {scene ? new Date(scene.created_at).toLocaleString() : '-'}</div>
                    <div><strong>最后更新:</strong> {scene ? new Date(scene.updated_at).toLocaleString() : '-'}</div>
                    <Button type="link" onClick={() => setShowSettings(true)} icon={<SettingOutlined />}>
                      编辑场景配置
                    </Button>
                  </div>
                </Card>
              ),
            },
          ]} />
        </Col>
      </Row>

      <Modal title="场景设置" open={showSettings} onCancel={() => setShowSettings(false)} width={800} footer={null}>
        <SceneSettings
          scene={scene}
          devices={devices || []}
          onUpdateScene={updateSceneConfig}
          onUpdateDevice={updateDeviceConfig}
          onClose={() => setShowSettings(false)}
        />
      </Modal>
    </div>
  );

  function handleDeviceSelect(deviceId: number) {
    setSelectedDeviceId(deviceId);
  }
};

// ==================== 站点选择总览 ====================
const StationOverview: React.FC<{ onSelect: (id: number) => void }> = ({ onSelect }) => {
  const [stations, setStations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const nav = useNavigate();

  useEffect(() => {
    (async () => {
      try {
        const res = await stationAPI.businessList();
        setStations(res.data?.items || []);
      } catch {
        message.error('加载站点列表失败');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px' }}>
        <Spin size="large" tip="加载站点列表..." />
      </div>
    );
  }

  return (
    <div className="digital-twin-page">
      <Card className="page-header" bordered={false}>
        <h1 style={{ margin: 0 }}>
          <ApartmentOutlined style={{ marginRight: 8 }} />
          数字孪生 - 站点总览
        </h1>
        <div style={{ marginTop: 8, color: '#666' }}>
          选择站点进入3D可视化视图
        </div>
      </Card>

      {stations.length === 0 ? (
        <Card style={{ marginTop: 16, textAlign: 'center', padding: '60px' }}>
          <ApartmentOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />
          <div style={{ marginTop: 16, fontSize: 16, color: '#999' }}>暂无站点数据</div>
          <Button type="primary" style={{ marginTop: 16 }} onClick={() => nav('/stations')}>
            前往站点管理
          </Button>
        </Card>
      ) : (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          {stations.map((s: any) => (
            <Col key={s.id} xs={24} sm={12} md={8} lg={6}>
              <Card
                hoverable
                className="station-card"
                onClick={() => onSelect(s.id)}
                style={{ borderRadius: 8, overflow: 'hidden' }}
              >
                <div style={{
                  height: 120,
                  background: 'linear-gradient(135deg, #1e1918 0%, #252120 100%)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: 12,
                  borderRadius: 4,
                }}>
                  <ApartmentOutlined style={{ fontSize: 48, color: '#ff5a36' }} />
                </div>
                <h3 style={{ margin: '0 0 8px' }}>{s.name}</h3>
                <div style={{ color: '#666', fontSize: 13, marginBottom: 4 }}>
                  {s.address || '未设置地址'}
                </div>
                <div style={{ color: '#999', fontSize: 12 }}>
                  ID: {s.id} | {s.device_count ?? '-'} 台设备
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
};

export default DigitalTwinPage;
