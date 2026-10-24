/**
 * 遥测数据页面 - 数据库版
 */
import React, { useState, useEffect } from 'react';
import { 
  Card, Table, Button, Space, Select, Row, Col, Statistic, 
  Progress, Tag, Modal, Tabs, Typography, Spin, message, Tooltip
} from 'antd';
import { 
  LineChartOutlined, ReloadOutlined, DashboardOutlined,
  ThunderboltOutlined, AlertOutlined, BarChartOutlined, WarningOutlined
} from '@ant-design/icons';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer]);
import { deviceAPI, telemetryAPI } from '../../api';

const { Option } = Select;
const { Text, Title } = Typography;

interface TelemetryData {
  id: number;
  device_id: number;
  device_name: string;
  device_type: string;
  timestamp: string;
  grid_voltage_a?: number;
  grid_voltage_b?: number;
  grid_voltage_c?: number;
  grid_current_a?: number;
  grid_current_b?: number;
  grid_current_c?: number;
  grid_power_a?: number;
  grid_power_b?: number;
  grid_power_c?: number;
  grid_power_total?: number;
  grid_frequency?: number;
  grid_power_factor?: number;
  battery_voltage?: number;
  battery_current?: number;
  battery_power?: number;
  battery_soc?: number;
  battery_soh?: number;
  battery_temperature?: number;
  pv1_voltage?: number;
  pv1_current?: number;
  pv1_power?: number;
  pv_power_total?: number;
  charger_voltage?: number;
  charger_current?: number;
  charger_power?: number;
  charger_soc?: number;
  gun_status?: number;
  gun_temperature?: number;
  internal_temperature?: number;
  ambient_temperature?: number;
}

interface Device {
  id: number;
  name: string;
  type: string;
  station_id: number;
  status: string;
}

const TelemetryPage: React.FC = () => {
  const [devices, setDevices] = useState<Device[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<number | undefined>();
  const [telemetryData, setTelemetryData] = useState<TelemetryData | null>(null);
  const [historyData, setHistoryData] = useState<TelemetryData[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);

  useEffect(() => {
    fetchDevices();
  }, []);

  useEffect(() => {
    if (selectedDevice) {
      fetchLatestTelemetry();
      fetchHistoryTelemetry();
    }
  }, [selectedDevice]);

  // 自动刷新
  useEffect(() => {
    if (!autoRefresh || !selectedDevice) return;
    const timer = setInterval(() => {
      fetchLatestTelemetry();
    }, 5000);
    return () => clearInterval(timer);
  }, [autoRefresh, selectedDevice]);

  const fetchDevices = async () => {
    try {
      const response: any = await deviceAPI.list();
      setDevices(response.items || []);
      if (response.items && response.items.length > 0) {
        setSelectedDevice(response.items[0].id);
      }
    } catch (error: any) {
      message.error('获取设备列表失败');
    }
  };

  const fetchLatestTelemetry = async () => {
    if (!selectedDevice) return;
    setLoading(true);
    try {
      const response: any = await telemetryAPI.latest(selectedDevice);
      if (response && response.device_id) {
        setTelemetryData(response);
      } else {
        setTelemetryData(null);
      }
    } catch (error: any) {
      if (error.response?.status === 404) {
        setTelemetryData(null);
      } else {
        message.error('获取遥测数据失败');
      }
    } finally {
      setLoading(false);
    }
  };

  const fetchHistoryTelemetry = async () => {
    if (!selectedDevice) return;
    setLoadingHistory(true);
    try {
      const response: any = await telemetryAPI.history(selectedDevice, { page: 1, page_size: 50 });
      setHistoryData(response.items || []);
    } catch (error: any) {
      setHistoryData([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleSimulate = async () => {
    if (!selectedDevice) {
      message.warning('请先选择设备');
      return;
    }
    try {
      await telemetryAPI.simulate(selectedDevice);
      message.success('模拟数据已生成');
      fetchLatestTelemetry();
      fetchHistoryTelemetry();
    } catch (error: any) {
      message.error('模拟数据生成失败');
    }
  };

  const typeTextMap: Record<string, string> = {
    CHARGER_DC: '直流充电桩',
    CHARGER_AC: '交流充电桩',
    PV_INVERTER: '光伏逆变器',
    BATTERY_INVERTER: '储能逆变器',
    PCS: '储能变流器',
    BATTERY: '储能电池柜',
    METER: '电表',
    GATEWAY: '网关',
  };

  const historyColumns = [
    { title: '时间', dataIndex: 'timestamp', key: 'timestamp', width: 180 },
    { title: '电网A相电压(V)', dataIndex: 'grid_voltage_a', key: 'grid_voltage_a', width: 120 },
    { title: '电网B相电压(V)', dataIndex: 'grid_voltage_b', key: 'grid_voltage_b', width: 120 },
    { title: '电网C相电压(V)', dataIndex: 'grid_voltage_c', key: 'grid_voltage_c', width: 120 },
    { title: '总功率(kW)', dataIndex: 'grid_power_total', key: 'grid_power_total', width: 100 },
    { title: '频率(Hz)', dataIndex: 'grid_frequency', key: 'grid_frequency', width: 100 },
    { title: '电池电压(V)', dataIndex: 'battery_voltage', key: 'battery_voltage', width: 100 },
    { title: '电池SOC(%)', dataIndex: 'battery_soc', key: 'battery_soc', width: 100 },
    { title: '光伏功率(kW)', dataIndex: 'pv_power_total', key: 'pv_power_total', width: 100 },
  ];

  // ECharts配置 - 电压趋势
  const voltageOption = {
    title: { text: '电压趋势', left: 'center' },
    tooltip: { trigger: 'axis' },
    legend: { data: ['A相', 'B相', 'C相'], bottom: 0 },
    xAxis: {
      type: 'category',
      data: historyData.map(d => d.timestamp?.slice(11, 19) || ''),
    },
    yAxis: { type: 'value', name: '电压(V)' },
    series: [
      { name: 'A相', type: 'line', data: historyData.map(d => d.grid_voltage_a) },
      { name: 'B相', type: 'line', data: historyData.map(d => d.grid_voltage_b) },
      { name: 'C相', type: 'line', data: historyData.map(d => d.grid_voltage_c) },
    ],
  };

  // ECharts配置 - 功率趋势
  const powerOption = {
    title: { text: '功率趋势', left: 'center' },
    tooltip: { trigger: 'axis' },
    legend: { data: ['总功率', '光伏功率', '电池功率'], bottom: 0 },
    xAxis: {
      type: 'category',
      data: historyData.map(d => d.timestamp?.slice(11, 19) || ''),
    },
    yAxis: { type: 'value', name: '功率(kW)' },
    series: [
      { name: '总功率', type: 'line', data: historyData.map(d => d.grid_power_total) },
      { name: '光伏功率', type: 'line', data: historyData.map(d => d.pv_power_total) },
      { name: '电池功率', type: 'line', data: historyData.map(d => d.battery_power) },
    ],
  };

  // ECharts配置 - SOC趋势
  const socOption = {
    title: { text: 'SOC趋势', left: 'center' },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: historyData.map(d => d.timestamp?.slice(11, 19) || ''),
    },
    yAxis: { type: 'value', name: '%', min: 0, max: 100 },
    series: [
      {
        name: 'SOC',
        type: 'line',
        data: historyData.map(d => d.battery_soc || d.charger_soc || 0),
        smooth: true,
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: '#f5a623' },
              { offset: 1, color: '#f5a62300' },
            ],
          },
        },
      },
    ],
  };

  // ECharts配置 - 温度趋势
  const tempOption = {
    title: { text: '温度趋势', left: 'center' },
    tooltip: { trigger: 'axis' },
    legend: { data: ['机内温度', '环境温度'], bottom: 0 },
    xAxis: {
      type: 'category',
      data: historyData.map(d => d.timestamp?.slice(11, 19) || ''),
    },
    yAxis: { type: 'value', name: '℃' },
    series: [
      { name: '机内温度', type: 'line', data: historyData.map(d => d.internal_temperature || 0), smooth: true, lineStyle: { color: '#cf1322' } },
      { name: '环境温度', type: 'line', data: historyData.map(d => d.ambient_temperature || 0), smooth: true, lineStyle: { color: '#34a853' } },
    ],
  };

  return (
    <div className="page-container">
      <Card title="遥测数据监控" extra={
        <Space>
          <Select
            style={{ width: 200 }}
            placeholder="选择设备"
            value={selectedDevice}
            onChange={setSelectedDevice}
          >
            {devices.map(d => (
              <Option key={d.id} value={d.id}>
                {d.name} ({typeTextMap[d.type] || d.type})
              </Option>
            ))}
          </Select>
          <Button type={autoRefresh ? 'primary' : 'default'} onClick={() => setAutoRefresh(!autoRefresh)}>
            {autoRefresh ? '停止刷新' : '自动刷新'}
          </Button>
          <Button icon={<ReloadOutlined />} onClick={fetchLatestTelemetry}>刷新</Button>
          <Button type="primary" onClick={handleSimulate}>生成模拟数据</Button>
        </Space>
      }>
        <Spin spinning={loading}>
          {telemetryData ? (
            <>
              <Row gutter={16} style={{ marginBottom: 24 }}>
                <Col span={6}>
                  <Card>
                    <Statistic
                      title="总功率"
                      value={telemetryData.grid_power_total || 0}
                      suffix="kW"
                      prefix={<ThunderboltOutlined />}
                    />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic
                      title="电网频率"
                      value={telemetryData.grid_frequency || 0}
                      suffix="Hz"
                      prefix={<DashboardOutlined />}
                    />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic
                      title="电池SOC"
                      value={telemetryData.battery_soc || 0}
                      suffix="%"
                      prefix={<AlertOutlined />}
                    />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic
                      title="光伏功率"
                      value={telemetryData.pv_power_total || 0}
                      suffix="kW"
                      prefix={<WarningOutlined />}
                    />
                  </Card>
                </Col>
              </Row>

              <Row gutter={16} style={{ marginBottom: 24 }}>
                <Col span={8}>
                  <Card title="电网侧数据">
                    <div>A相电压: {telemetryData.grid_voltage_a?.toFixed(1)} V</div>
                    <div>B相电压: {telemetryData.grid_voltage_b?.toFixed(1)} V</div>
                    <div>C相电压: {telemetryData.grid_voltage_c?.toFixed(1)} V</div>
                    <div>A相电流: {telemetryData.grid_current_a?.toFixed(1)} A</div>
                    <div>B相电流: {telemetryData.grid_current_b?.toFixed(1)} A</div>
                    <div>C相电流: {telemetryData.grid_current_c?.toFixed(1)} A</div>
                    <div>功率因数: {telemetryData.grid_power_factor?.toFixed(2)}</div>
                  </Card>
                </Col>
                <Col span={8}>
                  <Card title="电池侧数据">
                    <div>电压: {telemetryData.battery_voltage?.toFixed(1)} V</div>
                    <div>电流: {telemetryData.battery_current?.toFixed(1)} A</div>
                    <div>功率: {telemetryData.battery_power?.toFixed(1)} kW</div>
                    <div>SOC: {telemetryData.battery_soc?.toFixed(1)}%</div>
                    <div>SOH: {telemetryData.battery_soh?.toFixed(1)}%</div>
                    <div>温度: {telemetryData.battery_temperature?.toFixed(1)}°C</div>
                  </Card>
                </Col>
                <Col span={8}>
                  <Card title="光伏侧数据">
                    <div>PV1电压: {telemetryData.pv1_voltage?.toFixed(1)} V</div>
                    <div>PV1电流: {telemetryData.pv1_current?.toFixed(1)} A</div>
                    <div>PV1功率: {telemetryData.pv1_power?.toFixed(1)} kW</div>
                    <div>总功率: {telemetryData.pv_power_total?.toFixed(1)} kW</div>
                  </Card>
                </Col>
              </Row>
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Text type="secondary">暂无遥测数据，点击"生成模拟数据"按钮</Text>
            </div>
          )}
        </Spin>
      </Card>

      {/* 图表 */}
      {historyData.length > 0 && (
        <Row gutter={16} style={{ marginTop: 24 }}>
          <Col span={12}>
            <Card title="电压趋势图">
              <ReactEChartsCore echarts={echarts} option={voltageOption} style={{ height: 300 }} />
            </Card>
          </Col>
          <Col span={12}>
            <Card title="功率趋势图">
              <ReactEChartsCore echarts={echarts} option={powerOption} style={{ height: 300 }} />
            </Card>
          </Col>
        </Row>
      )}

      {historyData.length > 0 && (
        <Row gutter={16} style={{ marginTop: 24 }}>
          <Col span={12}>
            <Card title="SOC趋势图">
              <ReactEChartsCore echarts={echarts} option={socOption} style={{ height: 300 }} />
            </Card>
          </Col>
          <Col span={12}>
            <Card title="温度趋势图">
              <ReactEChartsCore echarts={echarts} option={tempOption} style={{ height: 300 }} />
            </Card>
          </Col>
        </Row>
      )}

      {/* 历史数据表格 */}
      <Card title="历史数据" style={{ marginTop: 24 }}>
        <Table
          columns={historyColumns}
          dataSource={historyData}
          rowKey="id"
          loading={loadingHistory}
          pagination={{ pageSize: 10 }}
        />
      </Card>
    </div>
  );
};

export default TelemetryPage;
