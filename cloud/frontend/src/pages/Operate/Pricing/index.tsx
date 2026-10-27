/**
 * 天链 V3 — 定价管理主页（Tab 切换 6 个子页面）
 *
 * 1. 时段定义  2. 充电费  3. 服务费
 * 4. 停车费    5. 占桩费  6. 预约费
 */
import React, { useState } from 'react';
import { Tabs } from 'antd';
import {
  ClockCircleOutlined, ThunderboltOutlined, CustomerServiceOutlined,
  CarOutlined, WarningOutlined, ScheduleOutlined, BankOutlined,
} from '@ant-design/icons';
import V2GPricing from './V2GPricing';
import PlatformFeePricing from './PlatformFeePricing';
import ChargingFeePricing from './ChargingFeePricing';
import TimeSlotDefinitions from './TimeSlotDefinitions';
import EnergyPricing from './EnergyPricing';
import ServicePricing from './ServicePricing';
import ParkingPricing from './ParkingPricing';
import OccupancyPricing from './OccupancyPricing';
import ReservationPricing from './ReservationPricing';

const PricingPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('charging-fee');

  return (
    <Tabs
      activeKey={activeTab}
      onChange={setActiveTab}
      items={[
        {
          key: 'charging-fee',
          label: <span><ThunderboltOutlined /> 充电费</span>,
          children: <ChargingFeePricing />,
        },
        {
          key: 'v2g',
          label: <span><ThunderboltOutlined /> V2G放电价</span>,
          children: <V2GPricing />,
        },
        {
          key: 'platform-fee',
          label: <span><BankOutlined /> 平台费率(占桩/预约)</span>,
          children: <PlatformFeePricing />,
        },
      ]}
    />
  );
};

export default PricingPage;
