/**
 * 天链 V3 - Dashboard 设备类型分布（静态饼图）
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Space, Typography } from 'antd';
import { ApiOutlined } from '@ant-design/icons';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';

const { Text } = Typography;

const DeviceTypePanel: React.FC = () => {
  const { t } = useTranslation();

  return (
    <Card
      title={
        <Space>
          <ApiOutlined style={{ color: '#1890ff' }} />
          <Text>{t('dashboard.device_types')}</Text>
        </Space>
      }
      className="dash-card"
    >
      <ReactEChartsCore
        echarts={echarts}
        option={{
          tooltip: { trigger: 'item', formatter: `{b}: {c}${t('dashboard.device_units')} ({d}%)` },
          series: [{
            type: 'pie',
            radius: ['30%', '60%'],
            center: ['50%', '48%'],
            avoidLabelOverlap: true,
            label: { show: true, formatter: '{b}', fontSize: 10 },
            emphasis: { label: { show: true, fontSize: 14 } },
            data: [
              { value: 20, name: t('dashboard.device_type_pv'), itemStyle: { color: '#fac858' } },
              { value: 15, name: t('dashboard.device_type_pcs'), itemStyle: { color: '#5470c6' } },
              { value: 10, name: t('dashboard.device_type_charger'), itemStyle: { color: '#91cc75' } },
              { value: 8, name: t('dashboard.device_type_meter'), itemStyle: { color: '#ee6666' } },
              { value: 5, name: t('dashboard.device_type_sensor'), itemStyle: { color: '#73c0de' } },
            ],
          }],
        }}
        style={{ height: '200px', width: '100%' }}
        opts={{ renderer: 'svg' }}
      />
    </Card>
  );
};

export default DeviceTypePanel;
