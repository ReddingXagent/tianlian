/**
 * AI运维分析仪表板 (Phase36-Task2 增强版)
 * - 健康度趋势、故障预测、能效分析可视化
 * - 历史数据趋势图表
 * - 实时数据流可视化
 * - 多设备对比视图
 * - 自定义仪表盘布局
 */
import React, { useState } from 'react';
import { Tabs, Card } from 'antd';
import {
  DashboardOutlined,
  HeartOutlined,
  ThunderboltOutlined,
  LineChartOutlined,
  SettingOutlined,
  RobotOutlined,
  SwapOutlined,
  DotChartOutlined,
  AppstoreOutlined,
} from '@ant-design/icons';
import HealthDashboard from './HealthDashboard';
import EfficiencyAnalysis from './EfficiencyAnalysis';
import AnomalyDetection from './AnomalyDetection';
import MaintenanceOptimizer from './MaintenanceOptimizer';
import HistoryTrend from './HistoryTrend';
import RealtimeStream from './RealtimeStream';
import DeviceComparison from './DeviceComparison';
import DraggableDashboard from './DraggableDashboard';

const AnalyticsDashboardPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('health');

  return (
    <div style={{ padding: 0, height: '100%' }}>
      <Card 
        style={{ 
          background: '#fff', 
          borderRadius: 8, 
          height: '100%',
          boxShadow: '0 2px 8px rgba(0,0,0,0.06)'
        }}
        bodyStyle={{ padding: '16px' }}
      >
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          tabBarStyle={{ marginBottom: 16 }}
          items={[
            {
              key: 'health',
              label: (
                <span>
                  <HeartOutlined />
                  健康度趋势
                </span>
              ),
              children: <HealthDashboard />,
            },
            {
              key: 'efficiency',
              label: (
                <span>
                  <LineChartOutlined />
                  能效分析
                </span>
              ),
              children: <EfficiencyAnalysis />,
            },
            {
              key: 'anomaly',
              label: (
                <span>
                  <ThunderboltOutlined />
                  异常检测
                </span>
              ),
              children: <AnomalyDetection />,
            },
            {
              key: 'maintenance',
              label: (
                <span>
                  <SettingOutlined />
                  维护优化
                </span>
              ),
              children: <MaintenanceOptimizer />,
            },
            {
              key: 'history',
              label: (
                <span>
                  <LineChartOutlined />
                  历史趋势
                </span>
              ),
              children: <HistoryTrend />,
            },
            {
              key: 'realtime',
              label: (
                <span>
                  <DotChartOutlined />
                  实时数据流
                </span>
              ),
              children: <RealtimeStream />,
            },
            {
              key: 'compare',
              label: (
                <span>
                  <SwapOutlined />
                  设备对比
                </span>
              ),
              children: <DeviceComparison />,
            },
            {
              key: 'dashboard',
              label: (
                <span>
                  <AppstoreOutlined />
                  自定义仪表盘
                </span>
              ),
              children: <DraggableDashboard />,
            },
          ]}
        />
      </Card>
    </div>
  );
};

export default AnalyticsDashboardPage;