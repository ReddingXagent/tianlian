/**
 * 设备健康度趋势仪表板
 * 展示设备健康度评分、趋势图表、风险设备列表
 */
import React, { useState, useEffect } from 'react';
import {
  Row, Col, Card, Select, Spin, Statistic, Table, Tag, Progress, Space, Button, message
} from 'antd';
import {
  HeartOutlined, WarningOutlined, CheckCircleOutlined, ReloadOutlined, ArrowUpOutlined
} from '@ant-design/icons';
import * as echarts from 'echarts/core';
import { PieChart } from 'echarts/charts';
import { TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([PieChart, TitleComponent, TooltipComponent, LegendComponent, CanvasRenderer]);
import api from '../../api';

interface HealthData {
  device_id: number;
  device_name: string;
  overall_score: number;
  risk_level: string;
  trend: string;
  score_breakdown: Record<string, number>;
}

const HealthDashboard: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<number | null>(null);
  const [devices, setDevices] = useState<any[]>([]);
  const [healthData, setHealthData] = useState<HealthData | null>(null);
  const [healthTrendChart, setHealthTrendChart] = useState<echarts.ECharts | null>(null);

  useEffect(() => {
    loadDevices();
    initHealthTrendChart();
    return () => {
      healthTrendChart?.dispose();
    };
  }, []);

  useEffect(() => {
    if (selectedDevice) {
      loadHealthScore(selectedDevice);
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
      // 静默处理：设备列表加载失败不影响健康度交互
    }
  };

  const loadHealthScore = async (deviceId: number) => {
    setLoading(true);
    try {
      const res = await api.post('/analytics/health-score', { device_id: deviceId, days: 7 });
      if (res.data?.code === 200) {
        setHealthData(res.data.data);
        updateTrendChart(res.data.data);
      } else {
        message.info(res.data?.message || '无健康度数据');
        // 使用模拟数据演示
        setHealthData({
          device_id: deviceId,
          device_name: devices.find(d => d.id === deviceId)?.name || `设备${deviceId}`,
          overall_score: 85,
          risk_level: 'medium',
          trend: 'stable',
          score_breakdown: { battery: 90, temperature: 80, alarm: 75, efficiency: 88 },
        });
        updateTrendChart({
          overall_score: 85,
          score_breakdown: { battery: 90, temperature: 80, alarm: 75, efficiency: 88 },
        });
      }
    } catch (error) {
      message.error('加载健康度失败');
    }
    setLoading(false);
  };

  const initHealthTrendChart = () => {
    const chartDom = document.getElementById('health-trend-chart');
    if (chartDom) {
      const chart = echarts.init(chartDom);
      setHealthTrendChart(chart);
      // 初始配置
      chart.setOption({
        title: { text: '健康度评分分布', left: 'center', textStyle: { fontSize: 16 } },
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        legend: { orient: 'vertical', left: 'left', top: 'middle' },
        series: [
          {
            name: '健康度',
            type: 'pie',
            radius: ['40%', '70%'],
            avoidLabelOverlap: false,
            itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
            label: { show: false, position: 'center' },
            emphasis: {
              label: { show: true, fontSize: 20, fontWeight: 'bold' },
            },
            labelLine: { show: false },
            data: [],
          },
        ],
      });
    }
  };

  const updateTrendChart = (data: any) => {
    if (healthTrendChart) {
      const breakdown = data.score_breakdown || {};
      const chartData = Object.entries(breakdown).map(([key, value]) => ({
        name: key,
        value: value as number,
      }));
      healthTrendChart.setOption({
        series: [{ data: chartData }],
      });
    }
  };

  const getRiskColor = (level: string) => {
    switch (level) {
      case 'low': return 'green';
      case 'medium': return 'orange';
      case 'high': return 'red';
      case 'critical': return 'red';
      default: return 'default';
    }
  };

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'improving': return <ArrowUpOutlined style={{ color: 'green' }} />;
      case 'stable': return <CheckCircleOutlined style={{ color: 'blue' }} />;
      case 'degrading': return <WarningOutlined style={{ color: 'red' }} />;
      default: return null;
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
            <Button icon={<ReloadOutlined />} onClick={() => selectedDevice && loadHealthScore(selectedDevice)}>
              刷新
            </Button>
          </Space>
        </Col>

        {/* 健康度概览 */}
        <Col span={8}>
          <Card loading={loading}>
            <Statistic
              title="综合健康度"
              value={healthData?.overall_score || 0}
              suffix="分"
              prefix={<HeartOutlined />}
              valueStyle={{ color: healthData?.overall_score >= 80 ? '#3f8600' : '#cf1322' }}
            />
            <div style={{ marginTop: 12 }}>
              <Tag color={getRiskColor(healthData?.risk_level || 'unknown')}>
                风险等级: {healthData?.risk_level?.toUpperCase() || 'N/A'}
              </Tag>
              <span style={{ marginLeft: 8 }}>
                {getTrendIcon(healthData?.trend || 'unknown')} 趋势: {healthData?.trend || 'N/A'}
              </span>
            </div>
          </Card>
        </Col>

        {/* 健康度分项 */}
        <Col span={16}>
          <Card title="健康度评分分布" loading={loading}>
            <div id="health-trend-chart" style={{ width: '100%', height: 300 }} />
          </Card>
        </Col>

        {/* 分项进度 */}
        {healthData?.score_breakdown && (
          <Col span={24}>
            <Card title="分项评分详情">
              <Row gutter={[16, 16]}>
                {Object.entries(healthData.score_breakdown).map(([key, value]) => (
                  <Col span={6} key={key}>
                    <Progress
                      type="dashboard"
                      percent={value as number}
                      strokeColor={value >= 80 ? '#52c41a' : value >= 60 ? '#faad14' : '#f5222d'}
                      format={(percent) => `${key}: ${percent}`}
                    />
                  </Col>
                ))}
              </Row>
            </Card>
          </Col>
        )}
      </Row>
    </div>
  );
};

export default HealthDashboard;