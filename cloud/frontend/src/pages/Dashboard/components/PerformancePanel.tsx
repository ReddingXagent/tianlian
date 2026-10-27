/**
 * 天链 V3 - Dashboard 运维性能概览（静态雷达图）
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Space, Typography } from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';

const { Text } = Typography;

const PerformancePanel: React.FC = () => {
  const { t } = useTranslation();

  return (
    <Card
      title={
        <Space>
          <ThunderboltOutlined style={{ color: '#ff4d4f' }} />
          <Text>{t('dashboard.ops_performance')}</Text>
        </Space>
      }
      className="dash-card"
    >
      <ReactEChartsCore
        echarts={echarts}
        option={{
          radar: {
            indicator: [
              { name: t('dashboard.radar_online_rate'), max: 100 },
              { name: t('dashboard.radar_health'), max: 100 },
              { name: t('dashboard.radar_efficiency'), max: 100 },
              { name: t('dashboard.radar_response'), max: 100 },
              { name: t('dashboard.radar_completion'), max: 100 },
            ],
            center: ['50%', '50%'],
            radius: '65%',
            shape: 'polygon',
            splitNumber: 4,
            axisName: { color: '#666', fontSize: 9 },
          },
          series: [{
            type: 'radar',
            data: [{
              value: [93, 88, 85, 78, 82],
              name: t('dashboard.ops_score'),
              areaStyle: { color: 'rgba(24,144,255,0.2)' },
              lineStyle: { color: '#1890ff', width: 2 },
              itemStyle: { color: '#1890ff' },
            }],
          }],
        }}
        style={{ height: '200px', width: '100%' }}
        opts={{ renderer: 'svg' }}
      />
    </Card>
  );
};

export default PerformancePanel;
