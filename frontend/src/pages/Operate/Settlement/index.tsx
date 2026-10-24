/**
 * 天链 V3 — 结算对账主页 (Tab: 日结/支付对账/企业结算/互联互通)
 */
import React, { useState } from 'react';
import { Tabs } from 'antd';
import {
  CalendarOutlined, SwapOutlined, BankOutlined, ApiOutlined,
} from '@ant-design/icons';
import DailySettlementPage from './DailySettlement';
import ReconciliationPage from './Reconciliation';
import EnterpriseSettlementPage from './EnterpriseSettlement';
import InterconnectPage from './Interconnect';

const SettlementIndex: React.FC = () => {
  const [activeTab, setActiveTab] = useState('daily');

  return (
    <Tabs
      activeKey={activeTab}
      onChange={setActiveTab}
      items={[
        {
          key: 'daily',
          label: <span><CalendarOutlined /> 日结汇总</span>,
          children: <DailySettlementPage />,
        },
        {
          key: 'reconciliation',
          label: <span><SwapOutlined /> 支付对账</span>,
          children: <ReconciliationPage />,
        },
        {
          key: 'enterprise',
          label: <span><BankOutlined /> 企业结算</span>,
          children: <EnterpriseSettlementPage />,
        },
        {
          key: 'interconnect',
          label: <span><ApiOutlined /> 互联互通结算</span>,
          children: <InterconnectPage />,
        },
      ]}
    />
  );
};

export default SettlementIndex;
