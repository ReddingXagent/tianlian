/**
 * 天链 V3 - Dashboard 工单状态分布面板（饼图）
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Tag, Space, Typography } from 'antd';
import { ToolOutlined } from '@ant-design/icons';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import type { WorkOrderStats } from '../types';

const { Text } = Typography;

const WorkOrderPanel: React.FC<{ workOrderStats: WorkOrderStats | null }> = ({ workOrderStats }) => {
  const { t } = useTranslation();

  // 工单状态分布饼图配置
  const getWorkOrderDistributionOption = () => {
    return {
      title: {
        text: t('dashboard.workorder_distribution'),
        left: 'center',
        textStyle: {
          fontSize: 14,
          color: '#1890ff',
        },
      },
      tooltip: {
        trigger: 'item',
        formatter: '{b}: {c}' + t('dashboard.units') + ' ({d}%)',
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
          name: t('dashboard.workorder_status'),
          type: 'pie',
          radius: '55%',
          center: ['50%', '45%'],
          data: [
            {
              value: workOrderStats?.pending || 5,
              name: t('dashboard.pending'),
              itemStyle: { color: '#faad14' },
            },
            {
              value: workOrderStats?.in_progress || 3,
              name: t('dashboard.in_progress'),
              itemStyle: { color: '#1890ff' },
            },
            {
              value: workOrderStats?.completed || 8,
              name: t('dashboard.completed'),
              itemStyle: { color: '#52c41a' },
            },
            {
              value: workOrderStats?.closed || 12,
              name: t('dashboard.closed'),
              itemStyle: { color: '#d9d9d9' },
            },
            {
              value: workOrderStats?.cancelled || 2,
              name: t('dashboard.cancelled'),
              itemStyle: { color: '#ff4d4f' },
            },
          ],
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.5)',
            },
          },
        },
      ],
    };
  };

  const totalWorkOrders = (workOrderStats?.pending || 0) +
    (workOrderStats?.in_progress || 0) +
    (workOrderStats?.completed || 0) +
    (workOrderStats?.closed || 0) +
    (workOrderStats?.cancelled || 0);

  return (
    <Card
      title={
        <Space>
          <ToolOutlined style={{ color: '#1890ff' }} />
          <Text>{t('dashboard.workorder_distribution')}</Text>
        </Space>
      }
      className="dash-card"
      extra={
        <Space>
          <Tag color="orange">{t('dashboard.pending')} {workOrderStats?.pending || 0}</Tag>
          <Tag color="blue">{t('dashboard.in_progress')} {workOrderStats?.in_progress || 0}</Tag>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {t('dashboard.total')} {totalWorkOrders}{t('dashboard.units')}
          </Text>
        </Space>
      }
    >
      <ReactEChartsCore
        echarts={echarts}
        option={getWorkOrderDistributionOption()}
        style={{ height: '280px', width: '100%' }}
        opts={{ renderer: 'svg' }}
        notMerge={true}
      />
    </Card>
  );
};

export default WorkOrderPanel;
