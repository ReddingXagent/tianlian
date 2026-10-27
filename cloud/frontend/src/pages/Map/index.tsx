/**
 * 站点地图页面
 */
import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Input, List, Tag, Button, Space, Badge, Statistic, Modal, Descriptions, Divider, message, Spin } from 'antd';
import { SearchOutlined, EnvironmentOutlined, ThunderboltOutlined, DesktopOutlined, WarningOutlined } from '@ant-design/icons';

import { stationAPI } from '../../api';

const { Search } = Input;

const MapPage: React.FC = () => {
  const [searchText, setSearchText] = useState('');
  const [selectedStation, setSelectedStation] = useState<any>(null);
  const [detailVisible, setDetailVisible] = useState(false);
  const [stations, setStations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStations();
  }, []);

  const loadStations = async () => {
    setLoading(true);
    try {
      const { data: raw } = await stationAPI.businessList();
      const list = Array.isArray(raw) ? raw : (raw?.items || []);
      const formatted = list.map((s: any) => ({
        id: String(s.id),
        name: s.name || s.station_name,
        address: s.address || s.station_address || '',
        lat: s.latitude || s.lat || 31.23,
        lng: s.longitude || s.lng || 121.47,
        devices: s.device_count || s.devices || 0,
        online: s.online_count || s.online || 0,
        status: s.status || 'normal',
        power: s.power || s.current_power || 0,
      }));
      setStations(formatted.length > 0 ? formatted : []);
    } catch (err) {
      message.error('加载站点列表失败');
    } finally {
      setLoading(false);
    }
  };

  const filteredStations = stations.filter(s => 
    s.name.includes(searchText) || s.address.includes(searchText)
  );

  const handleStationClick = (station: any) => {
    setSelectedStation(station);
  };

  const getStatusTag = (status: string) => {
    const map: Record<string, { color: string; text: string }> = {
      normal: { color: 'green', text: '正常' },
      warning: { color: 'orange', text: '告警' },
      offline: { color: 'red', text: '离线' },
    };
    return map[status] || { color: 'default', text: status };
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Spin size="large" tip="加载站点数据..." />
      </div>
    );
  }

  if (stations.length === 0) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Card><div style={{ textAlign: 'center', color: '#a6a1a0' }}>暂无站点数据</div></Card>
      </div>
    );
  }

  return (
    <div>
      <Row gutter={16}>
        {/* 左侧站点列表 */}
        <Col xs={24} lg={6}>
          <Card 
            title={
              <Space>
                <EnvironmentOutlined />
                站点列表
              </Space>
            }
            extra={<Badge count={stations.length} />}
          >
            <Search
              placeholder="搜索站点"
              prefix={<SearchOutlined />}
              onChange={e => setSearchText(e.target.value)}
              style={{ marginBottom: 16 }}
            />
            
            <List
              dataSource={filteredStations}
              renderItem={item => (
                <List.Item
                  style={{ 
                    cursor: 'pointer', 
                    background: selectedStation?.id === item.id ? '#faf5f4' : 'transparent',
                    borderRadius: 4,
                    padding: '8px 12px',
                    marginBottom: 8,
                  }}
                  onClick={() => handleStationClick(item)}
                >
                  <List.Item.Meta
                    avatar={<EnvironmentOutlined style={{ fontSize: 20, color: '#ff5a36' }} />}
                    title={
                      <Space>
                        {item.name}
                        <Tag color={getStatusTag(item.status).color}>
                          {getStatusTag(item.status).text}
                        </Tag>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={0}>
                        <span style={{ fontSize: 12, color: '#a6a1a0' }}>{item.address}</span>
                        <Space size={8}>
                          <Tag icon={<DesktopOutlined />}>{item.devices} 设备</Tag>
                          <Tag color="green">{item.online} 在线</Tag>
                        </Space>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>

        {/* 中间地图区域 */}
        <Col xs={24} lg={12}>
          <Card 
            title="地图视图"
            extra={<Button type="link">全屏</Button>}
            style={{ height: '100%', minHeight: 600 }}
          >
            <div style={{ 
              height: 500, 
              background: 'linear-gradient(135deg, #fef0ed 0%, #faf5f4 100%)',
              borderRadius: 8,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              position: 'relative',
              border: '1px solid #d9d9d9',
            }}>
              {/* 模拟地图网格 */}
              <div style={{ 
                position: 'absolute', 
                inset: 20, 
                backgroundImage: 'radial-gradient(#ff5a36 1px, transparent 1px)',
                backgroundSize: '20px 20px',
                opacity: 0.3,
              }} />
              
              {/* 模拟地图上的站点标记 */}
              {stations.map((station, index) => {
                const top = 50 + Math.sin(index * 1.2) * 150;
                const left = 50 + Math.cos(index * 1.2) * 180;
                return (
                  <div
                    key={station.id}
                    style={{
                      position: 'absolute',
                      top: `${top}px`,
                      left: `${left}px`,
                      cursor: 'pointer',
                      transform: 'translate(-50%, -50%)',
                    }}
                    onClick={() => handleStationClick(station)}
                  >
                    <div style={{
                      width: 40,
                      height: 40,
                      borderRadius: '50%',
                      background: station.status === 'normal' ? '#34a853' : station.status === 'warning' ? '#f5a623' : '#ea4335',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#fff',
                      fontSize: 18,
                      boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
                      border: selectedStation?.id === station.id ? '3px solid #ff5a36' : '3px solid transparent',
                    }}>
                      <EnvironmentOutlined />
                    </div>
                    <div style={{
                      position: 'absolute',
                      top: 45,
                      left: '50%',
                      transform: 'translateX(-50%)',
                      whiteSpace: 'nowrap',
                      fontSize: 12,
                      fontWeight: 500,
                      background: '#fff',
                      padding: '2px 6px',
                      borderRadius: 4,
                      boxShadow: '0 1px 4px rgba(0,0,0,0.1)',
                    }}>
                      {station.name}
                    </div>
                  </div>
                );
              })}
              
              <div style={{ position: 'absolute', bottom: 20, left: 20, color: '#a6a1a0', fontSize: 12 }}>
                <Space>
                  <span>🟢 正常</span>
                  <span>🟡 告警</span>
                  <span>🔴 离线</span>
                </Space>
              </div>
            </div>
          </Card>
        </Col>

        {/* 右侧统计 */}
        <Col xs={24} lg={6}>
          <Card title="站点统计">
            <Statistic
              title="站点总数"
              value={stations.length}
              prefix={<EnvironmentOutlined />}
            />
            <Divider />
            <Statistic
              title="设备总数"
              value={stations.reduce((sum, s) => sum + s.devices, 0)}
              prefix={<DesktopOutlined />}
            />
            <Divider />
            <Statistic
              title="在线设备"
              value={stations.reduce((sum, s) => sum + s.online, 0)}
              valueStyle={{ color: '#34a853' }}
            />
            <Divider />
            <Statistic
              title="总功率"
              value={stations.reduce((sum, s) => sum + s.power, 0)}
              prefix={<ThunderboltOutlined />}
              suffix="kW"
            />
          </Card>

          <Card title="站点告警" style={{ marginTop: 16 }}>
            {stations.filter(s => s.status !== 'normal').map(s => (
              <div key={s.id} style={{ marginBottom: 8 }}>
                <Space>
                  <WarningOutlined style={{ color: '#f5a623' }} />
                  <span>{s.name}</span>
                  <Tag color={getStatusTag(s.status).color}>
                    {getStatusTag(s.status).text}
                  </Tag>
                </Space>
              </div>
            ))}
            {stations.every(s => s.status === 'normal') && (
              <div style={{ color: '#34a853' }}>所有站点运行正常</div>
            )}
          </Card>
        </Col>
      </Row>

      {/* 站点详情弹窗 */}
      <Modal
        title="站点详情"
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={[
          <Button key="control" type="primary">
            远程控制
          </Button>,
          <Button key="close" onClick={() => setDetailVisible(false)}>
            关闭
          </Button>,
        ]}
      >
        {selectedStation && (
          <Descriptions column={1}>
            <Descriptions.Item label="站点名称">{selectedStation.name}</Descriptions.Item>
            <Descriptions.Item label="地址">{selectedStation.address}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={getStatusTag(selectedStation.status).color}>
                {getStatusTag(selectedStation.status).text}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="设备数量">{selectedStation.devices}</Descriptions.Item>
            <Descriptions.Item label="在线设备">{selectedStation.online}</Descriptions.Item>
            <Descriptions.Item label="当前功率">{selectedStation.power} kW</Descriptions.Item>
            <Descriptions.Item label="坐标">
              {selectedStation.lat}, {selectedStation.lng}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default MapPage;