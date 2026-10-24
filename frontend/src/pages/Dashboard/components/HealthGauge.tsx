/**
 * 天链 V3 - Dashboard 健康度仪表盘
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Space, Typography } from 'antd';
import { HeartOutlined } from '@ant-design/icons';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import type { HealthData } from '../types';

const { Text } = Typography;

const HealthGauge: React.FC<{ healthData: HealthData | null }> = ({ healthData }) => {
  const { t } = useTranslation();
  const score = healthData?.avg_health_score || 88;

  return (
    <Card
      title={
        <Space>
          <HeartOutlined style={{ color: '#52c41a' }} />
          <Text>{t('dashboard.health_gauge')}</Text>
        </Space>
      }
      className="dash-card"
    >
      <ReactEChartsCore
        echarts={echarts}
        option={{
          series: [{
            type: 'gauge',
            startAngle: 200,
            endAngle: -20,
            min: 0,
            max: 100,
            splitNumber: 5,
            progress: { show: true, width: 12 },
            axisLine: {
              lineStyle: {
                width: 12,
                color: [
                  [0.3, '#ff4d4f'],
                  [0.6, '#fa8c16'],
                  [0.8, '#faad14'],
                  [1, '#f5a623'],
                ],
              },
            },
            axisTick: { show: false },
            splitLine: { show: false, length: 8 },
            axisLabel: { show: false },
            pointer: { show: true, length: '60%', width: 6 },
            detail: {
              valueAnimation: true,
              formatter: `{value}${t('dashboard.score_unit')}`,
              fontSize: 18,
              fontWeight: 'bold',
              color: score >= 90 ? '#f5a623' : score >= 70 ? '#fa8c16' : '#ff4d4f',
              offsetCenter: [0, '30%'],
            },
            data: [{ value: score, name: t('dashboard.health_score') }],
            title: { offsetCenter: [0, '65%'], fontSize: 12, color: '#999' },
          }],
        }}
        style={{ height: '280px', width: '100%' }}
        opts={{ renderer: 'svg' }}
      />
    </Card>
  );
};

export default HealthGauge;
