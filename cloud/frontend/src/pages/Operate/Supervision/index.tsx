/**
 * 天链 V3 — 管理后台 · 市政监管对接 (入口容器)
 * Tab: 监管配置 / 上报状态 / 合规检查
 */
import React from 'react';
import { Card, Tabs } from 'antd';
import { SettingOutlined, CloudSyncOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import Configs from './Configs';
import Reports from './Reports';
import Compliance from './Compliance';

const SupervisionIndex: React.FC = () => {
  return (
    <Card>
      <Tabs
        defaultActiveKey="configs"
        items={[
          {
            key: 'configs',
            label: <span><SettingOutlined /> 监管配置</span>,
            children: <Configs />,
          },
          {
            key: 'reports',
            label: <span><CloudSyncOutlined /> 上报状态</span>,
            children: <Reports />,
          },
          {
            key: 'compliance',
            label: <span><SafetyCertificateOutlined /> 合规检查</span>,
            children: <Compliance />,
          },
        ]}
      />
    </Card>
  );
};

export default SupervisionIndex;
