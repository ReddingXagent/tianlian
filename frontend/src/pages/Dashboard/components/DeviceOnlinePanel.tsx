/**
 * 天链 V3 - Dashboard 设备在线率面板（环形图）
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Tag, Space, Typography } from 'antd';
import { ApiOutlined } from '@ant-design/icons';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import type { StatsOverview } from '../../../types';

const { Text } = Typography;

const DeviceOnlinePanel: React.FC<{ overviewStats: StatsOverview | null }> = ({ overviewStats }) => {
  const { t } = useTranslation();

  // 设备在线率环形图配置
  const getDeviceOnlineRateOption = () => {
    const onlineRate = overviewStats?.devices.online_rate || 93;
    const offlineRate = 100 - onlineRate;

    return {
      title: {
        text: t('dashboard.device_online_rate'),
        left: 'center',
        textStyle: {
          fontSize: 14,
          color: '#1890ff',
        },
      },
      tooltip: {
        trigger: 'item',
        formatter: '{b}: {c}' + t('dashboard.device_units') + ' ({d}%)',
      },
      legend: {
        orient: 'horizontal',
        bottom: '5%',
        itemWidth: 12,
        itemHeight: 12,
        textStyle: {
          fontSize: 11,
        },
      },
      series: [
        {
          name: t('dashboard.device_status'),
          type: 'pie',
          radius: ['40%', '65%'],
          center: ['50%', '45%'],
          avoidLabelOverlap: false,
          label: {
            show: true,
            position: 'center',
            formatter: `${onlineRate}%`,
            fontSize: 20,
            fontWeight: 'bold',
            color: '#52c41a',
          },
          emphasis: {
            label: {
              show: true,
              fontSize: 24,
              fontWeight: 'bold',
            },
          },
          labelLine: {
            show: false,
          },
          data: [
            {
              value: overviewStats?.devices.online || 54,
              name: t('dashboard.online'),
              itemStyle: { color: '#52c41a' },
            },
            {
              value: overviewStats?.devices.fault || 2,
              name: t('dashboard.fault'),
              itemStyle: { color: '#ff4d4f' },
            },
            {
              value: overviewStats?.devices.maintenance || 2,
              name: t('dashboard.maintenance'),
              itemStyle: { color: '#faad14' },
            },
          ],
        },
      ],
    };
  };

  return (
    <Card
      title={
        <Space>
          <ApiOutlined style={{ color: '#1890ff' }} />
          <Text>{t('dashboard.device_online_rate')}</Text>
        </Space>
      }
      className="dash-card"
      extra={<Tag color="green">{overviewStats?.devices.online_rate || 93}%</Tag>}
    >
      <ReactEChartsCore
        echarts={echarts}
        option={getDeviceOnlineRateOption()}
        style={{ height: '280px', width: '100%' }}
        opts={{ renderer: 'svg' }}
        notMerge={true}
      />
    </Card>
  );
};

export default DeviceOnlinePanel;
