/**
 * 告警自愈引擎主页面
 *
 * 三个子页面：
 * 1. Rules - 自愈规则配置
 * 2. History - 执行历史
 * 3. Approvals - 审批管理
 */
import React, { useState } from 'react';
import { Tabs } from 'antd';
import {
  SafetyCertificateOutlined,
  HistoryOutlined,
  AuditOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import Rules from './Rules';
import History from './History';
import Approvals from './Approvals';

const HealingPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('rules');

  return (
    <div style={{ padding: 0 }}>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        style={{ background: '#fff', padding: '0 16px', borderRadius: 8 }}
        items={[
          {
            key: 'rules',
            label: (
              <span>
                <SafetyCertificateOutlined />
                自愈规则
              </span>
            ),
            children: <Rules />,
          },
          {
            key: 'history',
            label: (
              <span>
                <HistoryOutlined />
                执行历史
              </span>
            ),
            children: <History />,
          },
          {
            key: 'approvals',
            label: (
              <span>
                <AuditOutlined />
                审批管理
              </span>
            ),
            children: <Approvals />,
          },
        ]}
      />
    </div>
  );
};

export default HealingPage;
