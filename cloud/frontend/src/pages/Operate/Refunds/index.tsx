/**
 * 退款管理主页 — Tab: 待审核 / 历史记录
 */
import React, { useState } from 'react';
import { Tabs } from 'antd';
import { ClockCircleOutlined, HistoryOutlined } from '@ant-design/icons';
import PendingRefundsPage from './PendingRefunds';
import RefundHistoryPage from './RefundHistory';

const RefundsIndex: React.FC = () => {
  const [activeTab, setActiveTab] = useState('pending');

  return (
    <Tabs
      activeKey={activeTab}
      onChange={setActiveTab}
      items={[
        {
          key: 'pending',
          label: <span><ClockCircleOutlined /> 待审核</span>,
          children: <PendingRefundsPage />,
        },
        {
          key: 'history',
          label: <span><HistoryOutlined /> 历史记录</span>,
          children: <RefundHistoryPage />,
        },
      ]}
    />
  );
};

export default RefundsIndex;
