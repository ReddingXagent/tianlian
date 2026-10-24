/**
 * 异常检测仪表板
 * 实时监测设备异常、异常评分、根因分析
 */
import React, { useState, useEffect } from 'react';
import {
  Row, Col, Card, Select, Spin, Statistic, Table, Tag, Space, Button, message, Alert, List, Timeline
} from 'antd';
import {
  ThunderboltOutlined, WarningOutlined, BugOutlined, ReloadOutlined, ExclamationCircleOutlined
} from '@ant-design/icons';
import * as echarts from 'echarts/core';
import { PieChart } from 'echarts/charts';
import { TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([PieChart, TitleComponent, TooltipComponent, LegendComponent, CanvasRenderer]);
import api from '../../api';

interface AnomalyData {
  device_id: number;
  device_name: string;
  anomaly_score: number;
  detected_anomalies: any[];
  severity: string;
  root_causes: string[];
  suggested_actions: string[];
}

const AnomalyDetection: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<number | null>(null);
  const [devices, setDevices] = useState<any[]>([]);
  const [anomalyData, setAnomalyData] = useState<AnomalyData | null>(null);
  const [anomalyChart, setAnomalyChart] = useState<echarts.ECharts | null>(null);

  useEffect(() => {
    loadDevices();
    initAnomalyChart();
    return () => {
      anomalyChart?.dispose();
    };
  }, []);

  useEffect(() => {
    if (selectedDevice) {
      loadAnomalyData(selectedDevice);
    }
  }, [selectedDevice]);

  const loadDevices = async () => {
    try {
      const res = await api.get('/devices');
      if (res.data?.code === 200) {
        setDevices(res.data.data?.items || []);
        if (res.data.data?.items?.length > 0) {
          setSelectedDevice(res.data.data.items[0].id);
        }
      }
    } catch {
      // 静默处理：设备列表加载失败不影响异常检测交互
    }
  };

  const loadAnomalyData = async (deviceId: number) => {
    setLoading(true);
    try {
      const res = await api.post('/analytics/anomaly-detection', { device_id: deviceId, hours: 24 });
      if (res.data?.code === 200) {
        setAnomalyData(res.data.data);
        updateAnomalyChart(res.data.data.detected_anomalies);
      } else {
        message.info(res.data?.message || '无异常数据');
        // 使用模拟数据演示
        setAnomalyData({
          device_id: deviceId,
          device_name: devices.find(d => d.id === deviceId)?.name || `设备${deviceId}`,
          anomaly_score: 0.3,
          detected_anomalies: [
            { type: 'temperature', timestamp: '2026-05-27 10:00', severity: 'warning', description: '温度偏高42°C' },
            { type: 'voltage', timestamp: '2026-05-27 11:00', severity: 'low', description: '电压波动±5%' },
          ],
          severity: 'low',
          root_causes: ['散热风扇转速不足', '环境温度升高'],
          suggested_actions: ['检查风扇运行状态', '开启空调制冷'],
        });
        updateAnomalyChart([
          { type: 'temperature', severity: 'warning' },
          { type: 'voltage', severity: 'low' },
        ]);
      }
    } catch (error) {
      message.error('加载异常数据失败');
    }
    setLoading(false);
  };

  const initAnomalyChart = () => {
    const chartDom = document.getElementById('anomaly-chart');
    if (chartDom) {
      const chart = echarts.init(chartDom);
      setAnomalyChart(chart);
      chart.setOption({
        title: { text: '异常类型分布', left: 'center' },
        tooltip: { trigger: 'item' },
        series: [
          {
            type: 'pie',
            radius: '60%',
            data: [],
            emphasis: {
              itemStyle: {
                shadowBlur: 10,
                shadowOffsetX: 0,
                shadowColor: 'rgba(0, 0, 0, 0.5)',
              },
            },
          },
        ],
      });
    }
  };

  const updateAnomalyChart = (anomalies: any[]) => {
    if (anomalyChart) {
      const severityColors: Record<string, string> = {
        critical: '#f5222d',
        high: '#fa541c',
        warning: '#faad14',
        low: '#52c41a',
      };
      const groupedData = anomalies.reduce((acc, a) => {
        const key = a.type || a.severity;
        acc[key] = (acc[key] || 0) + 1;
        return acc;
      }, {} as Record<string, number>);
      const chartData = Object.entries(groupedData).map(([name, value]) => ({
        name,
        value,
        itemStyle: { color: severityColors[name] || '#1890ff' },
      }));
      anomalyChart.setOption({ series: [{ data: chartData }] });
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'red';
      case 'high': return 'orange';
      case 'warning': return 'gold';
      case 'low': return 'green';
      default: return 'default';
    }
  };

  return (
    <div>
      <Row gutter={[16, 16]}>
        {/* 设备选择 */}
        <Col span={24}>
          <Space>
            <Select
              style={{ width: 300 }}
              placeholder="选择设备"
              value={selectedDevice}
              onChange={setSelectedDevice}
              options={devices.map(d => ({ label: d.name, value: d.id }))}
            />
            <Button icon={<ReloadOutlined />} onClick={() => selectedDevice && loadAnomalyData(selectedDevice)}>
              检测
            </Button>
          </Space>
        </Col>

        {/* 异常评分 */}
        <Col span={8}>
          <Card loading={loading}>
            <Statistic
              title="异常评分"
              value={anomalyData?.anomaly_score || 0}
              suffix="(0-1)"
              prefix={<BugOutlined />}
              valueStyle={{ color: anomalyData?.anomaly_score > 0.5 ? '#f5222d' : '#52c41a' }}
            />
            <div style={{ marginTop: 12 }}>
              <Tag color={getSeverityColor(anomalyData?.severity || 'unknown')}>
                严重等级: {anomalyData?.severity?.toUpperCase() || 'N/A'}
              </Tag>
            </div>
          </Card>
        </Col>

        {/* 异常分布图表 */}
        <Col span={16}>
          <Card title="异常类型分布" loading={loading}>
            <div id="anomaly-chart" style={{ width: '100%', height: 200 }} />
          </Card>
        </Col>

        {/* 检测到的异常 */}
        <Col span={12}>
          <Card title="检测到的异常" loading={loading}>
            <Timeline
              items={(anomalyData?.detected_anomalies || []).map((a, idx) => ({
                color: getSeverityColor(a.severity),
                children: (
                  <div>
                    <Tag color={getSeverityColor(a.severity)}>{a.severity}</Tag>
                    <span style={{ fontWeight: 500 }}>{a.type}</span>
                    <div style={{ marginTop: 4, color: '#666' }}>
                      {a.description} ({a.timestamp})
                    </div>
                  </div>
                ),
              }))}
            />
          </Card>
        </Col>

        {/* 根因分析 */}
        <Col span={12}>
          <Card title="根因分析" loading={loading}>
            <List
              dataSource={anomalyData?.root_causes || []}
              renderItem={(item, idx) => (
                <List.Item>
                  <ExclamationCircleOutlined style={{ marginRight: 8, color: '#faad14' }} />
                  {item}
                </List.Item>
              )}
            />
          </Card>
        </Col>

        {/* 建议措施 */}
        <Col span={24}>
          <Card title="建议措施" loading={loading}>
            <Alert
              type="info"
              showIcon
              message="基于异常检测结果，建议采取以下措施："
            />
            <List
              style={{ marginTop: 12 }}
              dataSource={anomalyData?.suggested_actions || []}
              renderItem={(item, idx) => (
                <List.Item>
                  <Tag color="blue">{idx + 1}</Tag>
                  {item}
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default AnomalyDetection;