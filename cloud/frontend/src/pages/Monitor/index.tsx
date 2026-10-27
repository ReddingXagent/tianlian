/**
 * 天链 V3 - 动态监控页面
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Select, Space, Button, Progress, DatePicker, Tabs, Spin } from 'antd';
import AutoHeightTable from '../../components/AutoHeightTable';
import { 
  ThunderboltOutlined, RiseOutlined, FallOutlined, 
  AreaChartOutlined, BarChartOutlined, LineChartOutlined,
  ReloadOutlined
} from '@ant-design/icons';
import { deviceAPI, efficiencyAPI, telemetryAPI } from '../../api';

const { RangePicker } = DatePicker;
const { TabPane } = Tabs;
const { Option } = Select;

const MonitorPage: React.FC = () => {
  const [station, setStation] = useState('all');
  const [loading, setLoading] = useState(false);

  // 真实数据状态
  const [realtimeData, setRealtimeData] = useState({
    totalPower: 0,
    powerTrend: 0,
    todayGeneration: 0,
    todayConsumption: 0,
    gridImport: 0,
    gridExport: 0,
    efficiency: 0,
    onlineDevices: 0,
    totalDevices: 0,
  });

  const [deviceData, setDeviceData] = useState<any[]>([]);

  // 获取实时数据
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      // 获取设备列表
      const { data: devicesRes } = await deviceAPI.list();
      const devices = Array.isArray(devicesRes) ? devicesRes : devicesRes.items || [];

      // 计算实时数据
      const totalPower = (devices as any[]).reduce((sum: number, d: any) => sum + (d.power || 0), 0);
      const runningDevices = devices.filter((d: any) => d.status === 'online').length;
      const totalDevices = devices.length;

      // 每设备并行取真实效率（利用率）+ 最新温度统计；任一请求失败则该字段降级为 null（表格显示 —）。
      // 效率来源 efficiencyAPI.deviceEfficiency(utilization.current)，温度来源 telemetryAPI.stats。
      const enriched = await Promise.all((devices as any[]).map(async (d: any) => {
        let efficiency: number | null = null;
        let temp: number | null = null;
        try {
          const { data: eff } = await efficiencyAPI.deviceEfficiency(d.id);
          const cur = eff?.utilization?.current;
          efficiency = typeof cur === 'number' ? cur : null;
        } catch {
          /* 该设备无效率数据 → 表格降级显示 — */
        }
        try {
          const { data: tel } = await telemetryAPI.stats(d.id);
          const s = tel?.stats;
          const thermalAvg = s?.thermal?.avg_temp;
          const thermalInternal = s?.thermal?.avg_internal_temp;
          const batteryAvg = s?.battery?.avg_temp;
          temp = typeof thermalAvg === 'number'
            ? thermalAvg
            : typeof thermalInternal === 'number'
              ? thermalInternal
              : typeof batteryAvg === 'number'
                ? batteryAvg
                : null;
        } catch {
          /* 该设备无遥测数据 → 表格降级显示 — */
        }
        return { d, efficiency, temp };
      }));

      // 系统效率 = 有效率设备的效率均值（替代原硬编码 94.5）；无任何设备有效率数据时为 0
      const effValues = enriched
        .map((e) => e.efficiency)
        .filter((v): v is number => v !== null);
      const sysEfficiency = effValues.length > 0
        ? effValues.reduce((sum, v) => sum + v, 0) / effValues.length
        : 0;

      setRealtimeData({
        totalPower,
        powerTrend: totalDevices > 0 ? (runningDevices / totalDevices) * 100 : 0,
        todayGeneration: devices.filter((d: any) => d.type === 'inverter').reduce((sum: number, d: any) => sum + (d.total_energy || 0), 0),
        todayConsumption: 0,
        gridImport: 0,
        gridExport: 0,
        efficiency: sysEfficiency,
        onlineDevices: runningDevices,
        totalDevices,
      });

      // 转换设备数据
      setDeviceData(enriched.map(({ d, efficiency, temp }) => ({
        id: String(d.id),
        name: d.name,
        power: d.power || 0,
        efficiency,
        temp,
        status: d.status === 'online' ? 'running' : 'stopped',
      })));

    } catch {
      // 静默处理：监控数据加载失败保留上次数据
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    // 定时刷新：每30秒
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const columns = [
    { title: '设备名称', dataIndex: 'name', key: 'name' },
    { 
      title: '功率(kW)', 
      dataIndex: 'power', 
      key: 'power',
      render: (val: number) => (
        <span style={{ color: val >= 0 ? '#34a853' : '#ea4335', fontWeight: 500 }}>
          {val > 0 ? '+' : ''}{val.toFixed(1)}
        </span>
      )
    },
    {
      title: '效率',
      dataIndex: 'efficiency',
      key: 'efficiency',
      render: (val: number | null) => val == null
        ? '—'
        : <Progress percent={val} size="small" strokeColor={val > 90 ? '#34a853' : '#f5a623'} />
    },
    {
      title: '温度(°C)',
      dataIndex: 'temp',
      key: 'temp',
      render: (val: number | null) => (val == null ? '—' : val.toFixed(1)),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const map: Record<string, { color: string; text: string }> = {
          running: { color: 'green', text: '运行中' },
          stopped: { color: 'default', text: '已停止' },
          charging: { color: 'blue', text: '充电中' },
          discharging: { color: 'orange', text: '放电中' },
        };
        return <Tag color={map[status]?.color || 'default'}>{map[status]?.text || status}</Tag>;
      }
    },
  ];

  return (
    <div className="page-container">
      {loading && <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>}
      
      {/* 顶部筛选 */}
      <Card style={{ marginBottom: 16 }}>
        <Space>
          <Select value={station} onChange={setStation} style={{ width: 150 }}>
            <Option value="all">全部站点</Option>
            <Option value="1">浦东站</Option>
            <Option value="2">浦西站</Option>
          </Select>
          <RangePicker />
          <Button type="primary" icon={<ReloadOutlined />} onClick={fetchData}>刷新数据</Button>
          <Button>导出报表</Button>
        </Space>
      </Card>

      {/* 关键指标 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="当前总功率"
              value={realtimeData.totalPower}
              suffix="kW"
              prefix={<ThunderboltOutlined style={{ color: '#f5a623' }} />}
              valueStyle={{ color: '#f5a623' }}
            />
            <div style={{ color: realtimeData.powerTrend > 0 ? '#34a853' : '#ea4335' }}>
              {realtimeData.powerTrend > 0 ? <RiseOutlined /> : <FallOutlined />}
              在线率 {realtimeData.powerTrend.toFixed(1)}%
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="今日发电量"
              value={realtimeData.todayGeneration}
              suffix="kWh"
              prefix={<AreaChartOutlined style={{ color: '#34a853' }} />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="在线设备"
              value={realtimeData.onlineDevices}
              suffix={`/ ${realtimeData.totalDevices}`}
              prefix={<BarChartOutlined style={{ color: '#ff5a36' }} />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="系统效率"
              value={realtimeData.efficiency}
              suffix="%"
              prefix={<LineChartOutlined style={{ color: '#722ed1' }} />}
            />
            <Progress percent={realtimeData.efficiency} showInfo={false} strokeColor="#722ed1" />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* 功率流向图 */}
        <Col xs={24} lg={12}>
          <Card title="功率流向">
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Row justify="center" gutter={40}>
                <Col>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 24, color: '#f5a623', fontWeight: 'bold' }}>
                      {realtimeData.totalPower} kW
                    </div>
                    <div>光伏输入</div>
                  </div>
                </Col>
              </Row>
              <Row justify="space-between" style={{ marginTop: 40 }}>
                <Col>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 18, color: '#34a853', fontWeight: 'bold' }}>
                      +{realtimeData.gridExport} kW
                    </div>
                    <div>上网</div>
                  </div>
                </Col>
                <Col>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 18, color: '#ff5a36', fontWeight: 'bold' }}>
                      {realtimeData.gridImport} kW
                    </div>
                    <div>购电</div>
                  </div>
                </Col>
              </Row>
              <Row justify="center" style={{ marginTop: 40 }}>
                <Col>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 18, color: '#722ed1', fontWeight: 'bold' }}>
                      {realtimeData.todayConsumption} kWh
                    </div>
                    <div>负载用电</div>
                  </div>
                </Col>
              </Row>
            </div>
          </Card>
        </Col>

        {/* 设备状态 */}
        <Col xs={24} lg={12}>
          <Card title="设备运行状态">
            <AutoHeightTable
              scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
              dataSource={deviceData}
              columns={columns}
              rowKey="id"
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default MonitorPage;
