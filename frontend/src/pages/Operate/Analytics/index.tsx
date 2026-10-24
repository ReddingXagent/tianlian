/**
 * 天链 V3 — 运营分析 6大报表 (Tab 切换)
 *
 * 1. 营收总览  2. 费用占比  3. 用户收入
 * 4. 站点排行  5. 时段分析  6. 优惠效果
 */
import React, { useState } from 'react';
import { Tabs } from 'antd';
import {
  DollarOutlined, PieChartOutlined, TeamOutlined,
  BarChartOutlined, ClockCircleOutlined, GiftOutlined,
} from '@ant-design/icons';
import RevenueOverview from './RevenueOverview';
import FeeBreakdown from './FeeBreakdown';
import UserRevenue from './UserRevenue';
import StationRank from './StationRank';
import TimeSlotAnalysis from './TimeSlotAnalysis';
import CouponEffect from './CouponEffect';

const AnalyticsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('revenue');

  return (
    <Tabs
      activeKey={activeTab}
      onChange={setActiveTab}
      items={[
        {
          key: 'revenue',
          label: <span><DollarOutlined /> 营收总览</span>,
          children: <RevenueOverview />,
        },
        {
          key: 'fee-breakdown',
          label: <span><PieChartOutlined /> 费用占比</span>,
          children: <FeeBreakdown />,
        },
        {
          key: 'user-revenue',
          label: <span><TeamOutlined /> 用户收入</span>,
          children: <UserRevenue />,
        },
        {
          key: 'station-rank',
          label: <span><BarChartOutlined /> 站点排行</span>,
          children: <StationRank />,
        },
        {
          key: 'time-slot',
          label: <span><ClockCircleOutlined /> 时段分析</span>,
          children: <TimeSlotAnalysis />,
        },
        {
          key: 'coupon-effect',
          label: <span><GiftOutlined /> 优惠效果</span>,
          children: <CouponEffect />,
        },
      ]}
    />
  );
};

export default AnalyticsPage;
