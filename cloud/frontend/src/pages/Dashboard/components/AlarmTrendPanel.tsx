/**
 * 天链 V3 - Dashboard 告警趋势面板（7 天折线图）
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Tag, Space, Typography } from 'antd';
import { AlertOutlined } from '@ant-design/icons';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import type { AlarmStats } from '../types';

const { Text } = Typography;

interface AlarmTrendPoint {
  date: string;
  count: number;
}

const AlarmTrendPanel: React.FC<{
  alarmTrend: AlarmTrendPoint[];
  alarmStats: AlarmStats | null;
}> = ({ alarmTrend, alarmStats }) => {
  const { t } = useTranslation();

  // 告警趋势折线图配置
  const getAlarmTrendOption = () => {
    return {
      title: {
        text: t('dashboard.recent_7d_trend'),
        left: 'center',
        textStyle: {
          fontSize: 14,
          color: '#1890ff',
        },
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'shadow',
        },
      },
      grid: {
        left: '10%',
        right: '10%',
        top: '20%',
        bottom: '15%',
      },
      xAxis: {
        type: 'category',
        data: alarmTrend.map(t => t.date),
        axisLabel: {
          fontSize: 11,
        },
      },
      yAxis: {
        type: 'value',
        name: t('dashboard.alarm_count'),
        minInterval: 1,
        axisLabel: {
          fontSize: 11,
        },
      },
      series: [
        {
          name: t('dashboard.alarm_count'),
          type: 'line',
          data: alarmTrend.map(t => t.count),
          smooth: true,
          itemStyle: {
            color: '#ff4d4f',
          },
          lineStyle: {
            width: 2,
          },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(255,77,79,0.3)' },
                { offset: 1, color: 'rgba(255,77,79,0.05)' },
              ],
            },
          },
        },
      ],
    };
  };

  return (
    <Card
      title={
        <Space>
          <AlertOutlined style={{ color: '#ff4d4f' }} />
          <Text>{t('dashboard.alarm_trend')}</Text>
        </Space>
      }
      className="dash-card"
      extra={
        <Space>
          <Tag color="red">{t('dashboard.active')} {alarmStats?.active || 0}</Tag>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {t('dashboard.recent_7d_trend')}
          </Text>
        </Space>
      }
    >
      <ReactEChartsCore
        echarts={echarts}
        option={getAlarmTrendOption()}
        style={{ height: '280px', width: '100%' }}
        opts={{ renderer: 'svg' }}
        notMerge={true}
      />
    </Card>
  );
};

export default AlarmTrendPanel;
