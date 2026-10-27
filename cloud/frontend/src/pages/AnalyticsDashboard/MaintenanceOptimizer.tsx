/**
 * 维护优化器
 * 数据源: GET /api/v1/predictive-maintenance/dashboard (LSTM 故障预测 + 风险汇总)
 * 卡 980f4d94: 原 POST /analytics/maintenance-optimization 后端不存在且有 mock 兜底,
 * 改指既有预测性维护端点(语义最贴近, 零后端改动), 已移除假数据
 */
import React, { useState, useEffect } from 'react';
import {
  Row, Col, Card, Statistic, Table, Tag, Button, message, Space, List
} from 'antd';
import AutoHeightTable from '../../components/AutoHeightTable';
import {
  SafetyOutlined, ToolOutlined, ReloadOutlined, AlertOutlined
} from '@ant-design/icons';
import * as echarts from 'echarts/core';
import { PieChart } from 'echarts/charts';
import { TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

import api from '../../api';

echarts.use([PieChart, TitleComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

interface Prediction {
  device_id: number;
  device_name: string;
  prediction_time: string;
  failure_probability: number;
  failure_probability_display: string;
  risk_level: string;
  health_trend: string;
  rul_display: string;
  recommended_actions: string[];
  confidence: number;
}

interface MaintenanceDashboard {
  total_devices: number;
  predicted_devices: number;
  risk_summary: { low: number; medium: number; high: number; critical: number };
  predictions: Prediction[];
  model_status: Record<string, any>;
}

const MaintenanceOptimizer: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [dashboard, setDashboard] = useState<MaintenanceDashboard | null>(null);
  const [riskChart, setRiskChart] = useState<echarts.ECharts | null>(null);

  useEffect(() => {
    const chartDom = document.getElementById('maintenance-risk-chart');
    let chart: echarts.ECharts | null = null;
    if (chartDom) {
      chart = echarts.init(chartDom);
      setRiskChart(chart);
      chart.setOption({
        title: { text: '风险等级分布', left: 'center' },
        tooltip: { trigger: 'item', formatter: '{b}: {c} 台' },
        legend: { bottom: 0 },
        series: [
          {
            type: 'pie',
            radius: '50%',
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
    return () => {
      chart?.dispose();
    };
  }, []);

  const updateRiskChart = (summary: MaintenanceDashboard['risk_summary']) => {
    if (riskChart) {
      riskChart.setOption({
        series: [
          {
            data: [
              { name: '低风险', value: summary.low, itemStyle: { color: '#52c41a' } },
              { name: '中风险', value: summary.medium, itemStyle: { color: '#faad14' } },
              { name: '高风险', value: summary.high, itemStyle: { color: '#fa8c16' } },
              { name: '严重', value: summary.critical, itemStyle: { color: '#cf1322' } },
            ].filter(d => d.value > 0),
          },
        ],
      });
    }
  };

  const loadDashboard = async () => {
    setLoading(true);
    try {
      // 响应拦截器已解包 {code,data} → res.data 即仪表盘数据
      const res = await api.get('/predictive-maintenance/dashboard');
      const data = res.data as MaintenanceDashboard;
      setDashboard(data);
      updateRiskChart(data.risk_summary);
    } catch {
      message.error('加载维护预测数据失败');
    }
    setLoading(false);
  };

  useEffect(() => {
    loadDashboard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const getRiskColor = (level: string) => {
    switch (level) {
      case 'critical': return 'red';
      case 'high': return 'orange';
      case 'medium': return 'gold';
      case 'low': return 'green';
      default: return 'default';
    }
  };

  const riskLevelText: Record<string, string> = {
    low: '低风险', medium: '中风险', high: '高风险', critical: '严重',
  };

  const highRisk = (dashboard?.risk_summary?.high || 0) + (dashboard?.risk_summary?.critical || 0);
  const sortedPredictions = [...(dashboard?.predictions || [])].sort(
    (a, b) => b.failure_probability - a.failure_probability
  );

  return (
    <div>
      <Row gutter={[16, 16]}>
        {/* 操作栏 */}
        <Col span={24}>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadDashboard}>
              刷新
            </Button>
          </Space>
        </Col>

        {/* 概览 */}
        <Col span={6}>
          <Card loading={loading}>
            <Statistic
              title="设备总数"
              value={dashboard?.total_devices || 0}
              suffix="台"
              prefix={<SafetyOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={loading}>
            <Statistic
              title="已预测设备"
              value={dashboard?.predicted_devices || 0}
              suffix="台"
              prefix={<ToolOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={loading}>
            <Statistic
              title="高风险设备"
              value={highRisk}
              suffix="台"
              prefix={<AlertOutlined />}
              valueStyle={{ color: highRisk > 0 ? '#cf1322' : '#3f8600' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={loading}>
            <Statistic
              title="已训练模型"
              value={Object.values(dashboard?.model_status || {}).filter((m: any) => m?.trained).length}
              suffix="个"
              prefix={<ToolOutlined />}
            />
          </Card>
        </Col>

        {/* 风险分布图表 */}
        <Col span={12}>
          <Card title="风险等级分布" loading={loading}>
            <div id="maintenance-risk-chart" style={{ width: '100%', height: 250 }} />
          </Card>
        </Col>

        {/* 高风险设备维护建议 */}
        <Col span={12}>
          <Card title="高风险设备维护建议" loading={loading}>
            <List
              dataSource={sortedPredictions.filter(p => p.risk_level === 'high' || p.risk_level === 'critical')}
              locale={{ emptyText: '无高风险设备' }}
              renderItem={(p) => (
                <List.Item>
                  <List.Item.Meta
                    title={<Space><span>{p.device_name}</span><Tag color={getRiskColor(p.risk_level)}>{riskLevelText[p.risk_level] || p.risk_level}</Tag><Tag>{p.failure_probability_display}</Tag></Space>}
                    description={p.recommended_actions?.join('；') || '暂无建议'}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>

        {/* 预测明细 */}
        <Col span={24}>
          <Card title="设备故障预测排名" loading={loading}>
            <AutoHeightTable
              scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
              dataSource={sortedPredictions}
              rowKey="device_id"
              pagination={false}
              columns={[
                { title: '设备名称', dataIndex: 'device_name', key: 'device_name' },
                {
                  title: '风险等级',
                  dataIndex: 'risk_level',
                  key: 'risk_level',
                  render: (l: string) => <Tag color={getRiskColor(l)}>{riskLevelText[l] || l}</Tag>,
                },
                { title: '故障概率', dataIndex: 'failure_probability_display', key: 'failure_probability_display' },
                { title: '剩余寿命', dataIndex: 'rul_display', key: 'rul_display' },
                { title: '健康趋势', dataIndex: 'health_trend', key: 'health_trend' },
                {
                  title: '维护建议',
                  dataIndex: 'recommended_actions',
                  key: 'recommended_actions',
                  render: (actions: string[]) => actions?.join('；') || '-',
                },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default MaintenanceOptimizer;
