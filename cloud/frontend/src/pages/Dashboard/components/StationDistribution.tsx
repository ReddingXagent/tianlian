/**
 * 天链 V3 - Dashboard 站点设备分布（静态横向柱状图）
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Space, Typography } from 'antd';
import { EnvironmentOutlined } from '@ant-design/icons';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';

const { Text } = Typography;

const StationDistribution: React.FC = () => {
  const { t } = useTranslation();

  return (
    <Card
      title={
        <Space>
          <EnvironmentOutlined style={{ color: '#faad14' }} />
          <Text>{t('dashboard.station_devices')}</Text>
        </Space>
      }
      className="dash-card"
    >
      <ReactEChartsCore
        echarts={echarts}
        option={{
          tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
          grid: { left: '30%', right: '5%', top: '5%', bottom: '5%', containLabel: true },
          xAxis: { type: 'value', axisLabel: { fontSize: 9 } },
          yAxis: {
            type: 'category',
            data: [t('dashboard.station_a'), t('dashboard.station_b'), t('dashboard.station_c'), t('dashboard.station_d'), t('dashboard.station_e')],
            axisLabel: { fontSize: 9 },
          },
          series: [{
            type: 'bar',
            data: [
              { value: 28, itemStyle: { color: '#5470c6' } },
              { value: 22, itemStyle: { color: '#91cc75' } },
              { value: 18, itemStyle: { color: '#fac858' } },
              { value: 15, itemStyle: { color: '#ee6666' } },
              { value: 12, itemStyle: { color: '#73c0de' } },
            ],
            barWidth: '40%',
            label: { show: true, position: 'right', fontSize: 10, formatter: `{c}${t('dashboard.device_units')}` },
          }],
        }}
        style={{ height: '200px', width: '100%' }}
        opts={{ renderer: 'svg' }}
      />
    </Card>
  );
};

export default StationDistribution;
