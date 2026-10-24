/**
 * 智能诊断页面
 * 
 * 功能：
 * 1. 设备选择诊断
 * 2. 五维度健康度可视化
 * 3. 诊断分析结果展示
 * 4. 维修建议列表
 * 5. 历史趋势查看
 */
import React, { useState, useEffect } from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { RadarChart, LineChart, PieChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent, RadarComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([RadarChart, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, RadarComponent, CanvasRenderer]);
import {
  Card,
  Select,
  Button,
  Row,
  Col,
  Statistic,
  Table,
  Tag,
  Alert,
  Spin,
  Typography,
  Tabs,
  Progress,
  Space,
  Divider,
  message,
  Badge,
} from 'antd';
import {
  MedicineBoxOutlined,
  AlertOutlined,
  ToolOutlined,
  LineChartOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { diagnosisAPI, DiagnosisResult, BatchDiagnosisResult } from '../../api/diagnosis';
import api from '../../api';

const { Title, Text, Paragraph } = Typography;
const { TabPane } = Tabs;

const DiagnosisPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [devices, setDevices] = useState<any[]>([]);
  const [stations, setStations] = useState<any[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<number | null>(null);
  const [selectedStation, setSelectedStation] = useState<number | null>(null);
  const [diagnosisResult, setDiagnosisResult] = useState<DiagnosisResult | null>(null);
  const [batchResult, setBatchResult] = useState<BatchDiagnosisResult | null>(null);
  const [trendData, setTrendData] = useState<any>(null);

  useEffect(() => {
    loadDevices();
    loadStations();
    loadBatchDiagnosis();
  }, []);

  const loadDevices = async () => {
    try {
      const res = await api.get('/api/v1/devices');
      setDevices(res.data.items || res.data || []);
    } catch {
      // 静默处理：设备列表加载失败不影响诊断交互
    }
  };

  const loadStations = async () => {
    try {
      const res = await api.get('/api/v1/stations');
      setStations(res.data.items || res.data || []);
    } catch {
      // 静默处理：站点列表加载失败不影响诊断交互
    }
  };

  const loadBatchDiagnosis = async () => {
    setLoading(true);
    try {
      const result = await diagnosisAPI.diagnoseBatch({});
      setBatchResult(result);
    } catch {
      // 静默处理：批量诊断加载失败保留上次结果
    } finally {
      setLoading(false);
    }
  };

  const runDiagnosis = async () => {
    if (!selectedDevice) {
      message.warning('请先选择设备');
      return;
    }
    
    setLoading(true);
    try {
      const result = await diagnosisAPI.diagnoseDevice(selectedDevice);
      setDiagnosisResult(result);
      
      // 同时加载趋势数据
      const trend = await diagnosisAPI.getHealthTrend(selectedDevice, 30);
      setTrendData(trend);
      
      message.success('诊断完成！');
    } catch (error: any) {
      message.error(error.response?.data?.detail || '诊断失败');
    } finally {
      setLoading(false);
    }
  };

  const runStationDiagnosis = async () => {
    if (!selectedStation) {
      message.warning('请先选择站点');
      return;
    }
    
    setLoading(true);
    try {
      const result = await diagnosisAPI.diagnoseBatch({ station_id: selectedStation });
      setBatchResult(result);
      message.success('站点诊断完成！');
    } catch (error: any) {
      message.error(error.response?.data?.detail || '诊断失败');
    } finally {
      setLoading(false);
    }
  };

  // 五维度雷达图
  const radarOption = diagnosisResult ? {
    title: { text: '健康度五维度分析', left: 'center' },
    tooltip: {},
    radar: {
      indicator: [
        { name: '电气安全', max: 100 },
        { name: '热稳定性', max: 100 },
        { name: '通信可靠性', max: 100 },
        { name: '电能质量', max: 100 },
        { name: '机械寿命', max: 100 },
      ],
      shape: 'polygon',
      splitNumber: 5,
    },
    series: [{
      type: 'radar',
      data: [{
        value: [
          diagnosisResult.scores.electrical_safe,
          diagnosisResult.scores.thermal,
          diagnosisResult.scores.communication,
          diagnosisResult.scores.power_quality,
          diagnosisResult.scores.mechanical,
        ],
        name: '健康度评分',
        areaStyle: { color: 'rgba(24, 144, 255, 0.3)' },
        lineStyle: { color: '#ff5a36' },
        itemStyle: { color: '#ff5a36' },
      }],
    }],
  } : null;

  // 健康度趋势图
  const trendOption = trendData && trendData.trend_data.length > 0 ? {
    title: { text: '健康度变化趋势（最近30天）' },
    tooltip: { trigger: 'axis' },
    legend: { data: ['综合健康度', '电气安全', '热稳定性', '通信可靠性', '电能质量', '机械寿命'], bottom: 0 },
    xAxis: {
      type: 'category',
      data: trendData.trend_data.map(d => d.date),
    },
    yAxis: { type: 'value', min: 0, max: 100 },
    series: [
      {
        name: '综合健康度',
        type: 'line',
        data: trendData.trend_data.map(d => d.total_score),
        smooth: true,
        lineStyle: { width: 3 },
      },
      {
        name: '电气安全',
        type: 'line',
        data: trendData.trend_data.map(d => d.electrical),
        smooth: true,
      },
      {
        name: '热稳定性',
        type: 'line',
        data: trendData.trend_data.map(d => d.thermal),
        smooth: true,
      },
    ],
  } : null;

  // 批量诊断图表
  const batchHealthOption = batchResult ? {
    title: { text: '设备健康状态分布' },
    tooltip: { trigger: 'item' },
    legend: { top: '5%', left: 'center' },
    series: [{
      name: '健康状态',
      type: 'pie',
      radius: ['40%', '70%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
      label: { show: false, position: 'center' },
      emphasis: { label: { show: true, fontSize: 20, fontWeight: 'bold' } },
      labelLine: { show: false },
      data: [
        { value: batchResult.healthy_devices, name: '健康', itemStyle: { color: '#34a853' } },
        { value: batchResult.warning_devices, name: '亚健康', itemStyle: { color: '#f5a623' } },
        { value: batchResult.fault_devices, name: '故障', itemStyle: { color: '#fa8c16' } },
        { value: batchResult.critical_devices, name: '严重', itemStyle: { color: '#ea4335' } },
      ],
    }],
  } : null;

  // 风险等级颜色
  const getRiskColor = (level: string) => {
    const colors: Record<string, string> = {
      low: '#34a853',
      medium: '#f5a623',
      high: '#fa8c16',
      critical: '#ea4335',
    };
    return colors[level] || '#ff5a36';
  };

  // 诊断分析表格列
  const analysisColumns = [
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      width: 120,
    },
    {
      title: '问题',
      dataIndex: 'issue',
      key: 'issue',
    },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (severity: string) => (
        <Tag color={getRiskColor(severity)}>{severity.toUpperCase()}</Tag>
      ),
    },
    {
      title: '评分',
      dataIndex: 'score',
      key: 'score',
      width: 80,
      render: (score: number) => score ? <Progress percent={score} size="small" /> : '-',
    },
    {
      title: '建议操作',
      dataIndex: 'action',
      key: 'action',
      render: (action: string) => action || '-',
    },
  ];

  // 维修建议表格列
  const recommendationColumns = [
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 100,
      render: (priority: string) => (
        <Tag color={priority === 'high' ? '#ea4335' : '#f5a623'}>{priority.toUpperCase()}</Tag>
      ),
    },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      width: 120,
    },
    {
      title: '维修建议',
      dataIndex: 'action',
      key: 'action',
    },
    {
      title: '原因',
      dataIndex: 'reason',
      key: 'reason',
    },
  ];

  // summary 兜底：后端在无设备等场景可能返回不带 summary 的批量结果，避免渲染白屏
  const batchSummary = batchResult?.summary;

  return (
    <div style={{ padding: '24px' }}>
      <Title level={2}>
        <MedicineBoxOutlined /> 智能诊断中心
      </Title>
      
      {/* 批量诊断概览 */}
      <Spin spinning={loading}>
        {batchResult && (
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col xs={24} sm={12} lg={6}>
              <Card>
                <Statistic
                  title="设备总数"
                  value={batchResult.total_devices}
                  suffix="台"
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card>
                <Statistic
                  title="平均健康度"
                  value={batchResult.avg_health_score}
                  suffix="分"
                  precision={1}
                  valueStyle={{ color: batchResult.avg_health_score >= 90 ? '#34a853' : '#f5a623' }}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card>
                <Statistic
                  title="风险设备"
                  value={batchSummary?.risk_devices ?? 0}
                  suffix="台"
                  valueStyle={{ color: (batchSummary?.risk_devices ?? 0) > 0 ? '#ea4335' : '#34a853' }}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card>
                <Statistic
                  title="健康率"
                  value={batchSummary?.health_rate ?? 0}
                  suffix="%"
                  precision={1}
                  valueStyle={{ color: (batchSummary?.health_rate ?? 0) >= 80 ? '#34a853' : '#fa8c16' }}
                />
              </Card>
            </Col>
          </Row>
        )}
      </Spin>

      <Tabs defaultActiveKey="device">
        {/* 单设备诊断 */}
        <TabPane tab="设备诊断" key="device">
          <Card style={{ marginBottom: 16 }}>
            <Space>
              <Select
                style={{ width: 200 }}
                placeholder="选择设备"
                showSearch
                optionFilterProp="children"
                onChange={(value) => setSelectedDevice(value)}
                value={selectedDevice}
              >
                {devices.map(d => (
                  <Select.Option key={d.id} value={d.id}>
                    {d.name} ({d.sn})
                  </Select.Option>
                ))}
              </Select>
              <Button 
                type="primary" 
                icon={<MedicineBoxOutlined />}
                onClick={runDiagnosis}
                loading={loading}
              >
                开始诊断
              </Button>
            </Space>
          </Card>

          {diagnosisResult && (
            <>
              {/* 设备概览 */}
              <Alert
                type={diagnosisResult.risk_level === 'low' ? 'success' : 
                      diagnosisResult.risk_level === 'critical' ? 'error' : 'warning'}
                message={
                  <Space>
                    <Text strong>{diagnosisResult.device_name}</Text>
                    <Tag color={getRiskColor(diagnosisResult.risk_level)}>
                      {diagnosisResult.risk_level.toUpperCase()} 风险
                    </Tag>
                    <Text>综合健康度: {diagnosisResult.overall_health} 分</Text>
                  </Space>
                }
                style={{ marginBottom: 16 }}
              />

              {/* 统计卡片 */}
              <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                <Col xs={12} sm={6}>
                  <Card size="small">
                    <Statistic 
                      title="活跃告警" 
                      value={diagnosisResult.alarm_stats.active}
                      suffix={`/${diagnosisResult.alarm_stats.total}`}
                      valueStyle={{ color: diagnosisResult.alarm_stats.active > 0 ? '#ea4335' : '#34a853' }}
                    />
                  </Card>
                </Col>
                <Col xs={12} sm={6}>
                  <Card size="small">
                    <Statistic 
                      title="待处理工单" 
                      value={diagnosisResult.workorder_stats.pending}
                      suffix={`/${diagnosisResult.workorder_stats.total}`}
                    />
                  </Card>
                </Col>
                <Col xs={12} sm={6}>
                  <Card size="small">
                    <Statistic 
                      title="预估维修成本" 
                      value={diagnosisResult.estimated_cost.min}
                      suffix={`-${diagnosisResult.estimated_cost.max}元`}
                    />
                  </Card>
                </Col>
                <Col xs={12} sm={6}>
                  <Card size="small">
                    <Statistic 
                      title="预测故障数" 
                      value={diagnosisResult.predicted_failures.length}
                    />
                  </Card>
                </Col>
              </Row>

              {/* 五维度雷达图 */}
              <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                <Col xs={24} lg={12}>
                  <Card>
                    {radarOption && <ReactEChartsCore echarts={echarts} option={radarOption} style={{ height: 300 }} />}
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card>
                    {trendOption && <ReactEChartsCore echarts={echarts} option={trendOption} style={{ height: 300 }} />}
                  </Card>
                </Col>
              </Row>

              {/* 诊断分析 */}
              <Card title={<><AlertOutlined /> 诊断分析</>} style={{ marginBottom: 16 }}>
                <Table 
                  dataSource={diagnosisResult.analysis}
                  columns={analysisColumns}
                  rowKey={(record, index) => `${record.category}-${index}`}
                  pagination={false}
                  size="small"
                />
              </Card>

              {/* 维修建议 */}
              <Card title={<><ToolOutlined /> 维修建议</>} style={{ marginBottom: 16 }}>
                <Table 
                  dataSource={diagnosisResult.recommendations}
                  columns={recommendationColumns}
                  rowKey={(record, index) => `${record.category}-${index}`}
                  pagination={false}
                  size="small"
                />
              </Card>

              {/* 预测故障 */}
              {diagnosisResult.predicted_failures.length > 0 && (
                <Card title={<><WarningOutlined /> 预测故障</>}>
                  {diagnosisResult.predicted_failures.map((failure, index) => (
                    <Alert
                      key={index}
                      type={failure.probability === '高' ? 'error' : 'warning'}
                      message={`${failure.type} - ${failure.probability}概率`}
                      description={`预防措施: ${failure.preventive_action}`}
                      style={{ marginBottom: 8 }}
                    />
                  ))}
                </Card>
              )}
            </>
          )}
        </TabPane>

        {/* 站点诊断 */}
        <TabPane tab="站点诊断" key="station">
          <Card style={{ marginBottom: 16 }}>
            <Space>
              <Select
                style={{ width: 200 }}
                placeholder="选择站点"
                onChange={(value) => setSelectedStation(value)}
                value={selectedStation}
              >
                {stations.map(s => (
                  <Select.Option key={s.id} value={s.id}>
                    {s.name}
                  </Select.Option>
                ))}
              </Select>
              <Button 
                type="primary" 
                icon={<MedicineBoxOutlined />}
                onClick={runStationDiagnosis}
                loading={loading}
              >
                站点诊断
              </Button>
            </Space>
          </Card>

          {batchResult && batchHealthOption && (
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={8}>
                <Card>
                  <ReactEChartsCore echarts={echarts} option={batchHealthOption} style={{ height: 300 }} />
                </Card>
              </Col>
              <Col xs={24} lg={16}>
                <Card title="需关注设备">
                  <Table 
                    dataSource={batchResult.top_issues}
                    columns={[
                      { title: '设备名', dataIndex: 'device_name', key: 'device_name' },
                      { title: '健康度', dataIndex: 'health_score', key: 'health_score', 
                        render: (v: number) => <Progress percent={v} size="small" strokeColor={v < 60 ? '#ea4335' : '#f5a623'} /> },
                      { title: '告警数', dataIndex: 'alarm_count', key: 'alarm_count',
                        render: (v: number) => <Badge count={v} style={{ backgroundColor: '#ea4335' }} /> },
                      { title: '状态', dataIndex: 'status', key: 'status',
                        render: (v: string) => <Tag color={v === 'fault' ? '#ea4335' : '#fa8c16'}>{v}</Tag> },
                    ]}
                    rowKey="device_name"
                    pagination={false}
                    size="small"
                  />
                </Card>
              </Col>
            </Row>
          )}
        </TabPane>
      </Tabs>
    </div>
  );
};

export default DiagnosisPage;