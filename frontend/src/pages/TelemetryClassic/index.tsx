/**
 * 遥测数据页面 - 基于光储充设备协议分析
 *
 * 功能：
 * - 设备遥测数据实时展示
 * - 历史数据趋势图表
 * - 多维度数据统计
 */
import React from 'react';
import {
  Card, Button, Space, Select, Row, Col, Alert,
  Modal, Tabs, Table, Typography, Spin,
} from 'antd';
import {
  LineChartOutlined, ReloadOutlined, DashboardOutlined,
} from '@ant-design/icons';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer]);

import { useTelemetryData } from './hooks/useTelemetryData';
import GridCard from './components/GridCard';
import BatteryCard from './components/BatteryCard';
import PVCard from './components/PVCard';
import ChargerCard from './components/ChargerCard';
import TemperatureCard from './components/TemperatureCard';
import PowerTrendChart from './components/PowerTrendChart';
import SOCTrendChart from './components/SOCTrendChart';
import TemperatureTrendChart from './components/TemperatureTrendChart';

const { Option } = Select;
const { Text, Title } = Typography;

const TelemetryPage: React.FC = () => {
  const {
    devices,
    deviceError,
    fetchDevices,
    selectedDevice,
    setSelectedDevice,
    telemetry,
    historyData,
    loading,
    detailVisible,
    setDetailVisible,
    autoRefresh,
    setAutoRefresh,
    fetchLatestTelemetry,
  } = useTelemetryData();

  // 设备类型判断
  const isBatteryDevice = telemetry?.device_type?.includes('battery') ||
                          telemetry?.device_type === 'pcs';
  const isPVDevice = telemetry?.device_type?.includes('pv') ||
                     telemetry?.device_type === 'battery_inverter';
  const isChargerDevice = telemetry?.device_type?.includes('charger');

  return (
    <div style={{ padding: 24 }}>
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col span={8}>
            <Space>
              <DashboardOutlined />
              <Text strong>遥测数据监控</Text>
            </Space>
          </Col>
          <Col span={8}>
            <Select
              value={selectedDevice ?? undefined}
              onChange={setSelectedDevice}
              placeholder="选择设备"
              style={{ width: '100%' }}
            >
              {devices.map(d => (
                <Option key={d.id} value={d.id}>
                  {d.name}{d.type ? ` (${d.type})` : ''}
                </Option>
              ))}
            </Select>
          </Col>
          <Col span={8}>
            <Space style={{ float: 'right' }}>
              <Button
                type={autoRefresh ? 'primary' : 'default'}
                onClick={() => setAutoRefresh(!autoRefresh)}
              >
                {autoRefresh ? '停止刷新' : '自动刷新'}
              </Button>
              <Button icon={<ReloadOutlined />} onClick={fetchLatestTelemetry}>
                刷新
              </Button>
              <Button icon={<LineChartOutlined />} onClick={() => setDetailVisible(true)}>
                详情
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {deviceError && (
        <Alert type="error" showIcon style={{ marginBottom: 16 }}
          message="设备列表加载失败" description={deviceError}
          action={<Button size="small" icon={<ReloadOutlined />} onClick={fetchDevices}>重试</Button>}
        />
      )}

      {loading ? (
        <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
      ) : (
        <>
          {/* 根据设备类型显示不同数据卡片 */}
          {(isBatteryDevice || isPVDevice) && <GridCard telemetry={telemetry} />}
          {isBatteryDevice && <BatteryCard telemetry={telemetry} />}
          {isPVDevice && <PVCard telemetry={telemetry} />}
          {isChargerDevice && <ChargerCard telemetry={telemetry} />}
          <TemperatureCard telemetry={telemetry} />

          {/* 趋势图 */}
          <Card title="趋势分析">
            <Tabs
              defaultActiveKey="power"
              items={[
                { key: 'power', label: '功率趋势', children: <PowerTrendChart historyData={historyData} /> },
                { key: 'soc', label: 'SOC趋势', children: <SOCTrendChart historyData={historyData} /> },
                { key: 'temp', label: '温度趋势', children: <TemperatureTrendChart historyData={historyData} /> },
              ]}
            />
          </Card>
        </>
      )}

      {/* 详细数据弹窗 */}
      <Modal
        title="遥测数据详情"
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        width={800}
        footer={null}
      >
        <Tabs
          defaultActiveKey="current"
          items={[
            {
              key: 'current',
              label: '当前数据',
              children: (
                <Table
                  dataSource={Object.entries(telemetry || {}).map(([key, value]) => ({
                    key,
                    value: typeof value === 'number' ? value.toFixed(2) : value,
                  }))}
                  columns={[
                    { title: '参数', dataIndex: 'key', key: 'key' },
                    { title: '值', dataIndex: 'value', key: 'value' },
                  ]}
                  pagination={false}
                  size="small"
                />
              )
            },
            {
              key: 'protocol',
              label: '协议信息',
              children: (
                <Card>
                  <p><Text strong>协议类型：</Text>{isChargerDevice ? 'MQTT 3.1.1' : 'Modbus-RTU'}</p>
                  <p><Text strong>数据来源：</Text>{isChargerDevice ? 'tcu/{address}/report' : 'RS485 @ 9600bps'}</p>
                  <p><Text strong>采集周期：</Text>5秒</p>
                  <p><Text strong>最后更新：</Text>{telemetry?.timestamp}</p>
                </Card>
              )
            },
          ]}
        />
      </Modal>
    </div>
  );
};

export default TelemetryPage;
