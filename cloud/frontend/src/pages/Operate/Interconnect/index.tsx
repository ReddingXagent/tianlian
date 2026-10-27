/**
 * 天链 V3 — 管理后台 · 互联互通对接 (入口容器)
 * Tab: 平台管理 / 导流订单
 */
import React from 'react';
import { Card, Tabs } from 'antd';
import { ApiOutlined, ProfileOutlined } from '@ant-design/icons';
import Configs from './Configs';
import Orders from './Orders';

const InterconnectIndex: React.FC = () => {
  return (
    <Card>
      <Tabs
        defaultActiveKey="configs"
        items={[
          {
            key: 'configs',
            label: <span><ApiOutlined /> 平台管理</span>,
            children: <Configs />,
          },
          {
            key: 'orders',
            label: <span><ProfileOutlined /> 导流订单</span>,
            children: <Orders />,
          },
        ]}
      />
    </Card>
  );
};

export default InterconnectIndex;
