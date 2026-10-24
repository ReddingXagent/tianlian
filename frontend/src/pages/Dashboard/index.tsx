/**
 * 天链V3 Dashboard首页大屏 - Phase27改造版
 * 功能: 统计卡片 + 4个数据面板 + 30秒自动刷新
 *
 * 结构重构 (c56f2cee): 数据逻辑 → hooks/useDashboardData；
 *                      9 个面板 → components/*。纯结构性拆分，行为不变。
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Row, Col, Typography, Space, Tag, Tooltip } from 'antd';
import { DashboardOutlined, SyncOutlined } from '@ant-design/icons';
import * as echarts from 'echarts/core';
import { LineChart, PieChart, GaugeChart, BarChart, RadarChart } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, LegendComponent, TitleComponent, DataZoomComponent, PolarComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

import PageWrapper from '../../components/PageWrapper';
import EfficiencyOverviewCard from './EfficiencyOverviewCard';
import { useDashboardData } from './hooks/useDashboardData';
import StatCards from './components/StatCards';
import HealthPanel from './components/HealthPanel';
import AlarmTrendPanel from './components/AlarmTrendPanel';
import DeviceOnlinePanel from './components/DeviceOnlinePanel';
import WorkOrderPanel from './components/WorkOrderPanel';
import HealthGauge from './components/HealthGauge';
import DeviceTypePanel from './components/DeviceTypePanel';
import StationDistribution from './components/StationDistribution';
import PerformancePanel from './components/PerformancePanel';

echarts.use([
  LineChart, PieChart, GaugeChart, BarChart, RadarChart,
  GridComponent, TooltipComponent, LegendComponent, TitleComponent, DataZoomComponent, PolarComponent,
  CanvasRenderer,
]);

const { Title, Text } = Typography;

// ==================== 主组件 ====================
const Dashboard: React.FC = () => {
  const { t } = useTranslation();
  const {
    loading, refreshing, lastUpdate,
    overviewStats, healthData, alarmStats, workOrderStats, alarmTrend,
    wsConnected, connectionState,
    loadAllData,
  } = useDashboardData();

  return (
    <PageWrapper
      loading={loading && !overviewStats}
      skeletonType="dashboard"
      hasData={!!overviewStats}
      empty={{ type: 'default', title: '暂无数据', description: 'Dashboard 数据加载中...' }}
      transition="slide-up"
    >
      <div className="dash-container">
        {/* 顶部标题栏 */}
        <div className="dash-header">
          <Space>
            <DashboardOutlined style={{ fontSize: 20, color: 'var(--primary-color)' }} />
            <Title level={4} style={{ margin: 0, color: 'var(--text-primary)' }}>运维中心 Dashboard</Title>
          </Space>

          <Space className="dash-header-info">
            <Tooltip title="手动刷新">
              <SyncOutlined
                spin={refreshing}
                onClick={() => loadAllData(true)}
                style={{
                  fontSize: 16,
                  color: 'var(--primary-color)',
                  cursor: 'pointer',
                }}
              />
            </Tooltip>
            <Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              最后更新: {lastUpdate.toLocaleTimeString('zh-CN')}
            </Text>
            <Tag color="blue">自动刷新: 30秒</Tag>
            <Tag
              color={wsConnected ? 'green' : connectionState === 'connecting' ? 'blue' : 'red'}
              style={{ fontSize: 11 }}
            >
              {wsConnected ? '实时' : connectionState === 'connecting' ? '连接中' : '未连接'}
            </Tag>
          </Space>
        </div>

        {/* 统计数据卡片区域 */}
        <StatCards overviewStats={overviewStats} />

        {/* Phase48: 运行效率概览 */}
        <div style={{ marginTop: 24 }}>
          <EfficiencyOverviewCard refreshInterval={60000} />
        </div>

        {/* 数据面板区域 */}
        <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
          <Col xs={24} lg={12}>
            <HealthPanel healthData={healthData} />
          </Col>

          <Col xs={24} lg={12}>
            <AlarmTrendPanel alarmTrend={alarmTrend} alarmStats={alarmStats} />
          </Col>

          <Col xs={24} lg={12}>
            <DeviceOnlinePanel overviewStats={overviewStats} />
          </Col>

          <Col xs={24} lg={12}>
            <WorkOrderPanel workOrderStats={workOrderStats} />
          </Col>
        </Row>

        {/* Phase36-Task2: 新增可视化面板 */}
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} lg={6}>
            <HealthGauge healthData={healthData} />
          </Col>
          <Col xs={24} lg={6}>
            <DeviceTypePanel />
          </Col>
          <Col xs={24} lg={6}>
            <StationDistribution />
          </Col>
          <Col xs={24} lg={6}>
            <PerformancePanel />
          </Col>
        </Row>

        {/* 底部说明 */}
        <div className="dash-footer">
          <Text style={{ color: 'var(--text-tertiary)', fontSize: 12 }}>
            {t('dashboard.footer')}
          </Text>
        </div>
      </div>
    </PageWrapper>
  );
};

export default Dashboard;
