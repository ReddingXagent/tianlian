/**
 * 订单管理主页 — Tab: 全部订单 / 异常订单
 */
import React, { useState } from 'react';
import { Tabs } from 'antd';
import { ShoppingCartOutlined, WarningOutlined } from '@ant-design/icons';
import OrderListPage from './OrderList';
import AbnormalOrdersPage from './AbnormalOrders';

const OrdersIndex: React.FC = () => {
  const [activeTab, setActiveTab] = useState('all');

  return (
    <Tabs
      activeKey={activeTab}
      onChange={setActiveTab}
      items={[
        {
          key: 'all',
          label: <span><ShoppingCartOutlined /> 全部订单</span>,
          children: <OrderListPage />,
        },
        {
          key: 'abnormal',
          label: <span><WarningOutlined /> 异常订单</span>,
          children: <AbnormalOrdersPage />,
        },
      ]}
    />
  );
};

export default OrdersIndex;
