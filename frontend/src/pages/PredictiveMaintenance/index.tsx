/**
 * 预测性维护页面
 *
 * 功能：
 * 1. Dashboard - 预测性维护仪表盘（设备健康度趋势、即将故障设备列表）
 * 2. Prediction - 设备预测（选择设备→一键预测→显示结果）
 * 3. Model - 模型管理（查看模型状态、触发训练）
 * 4. History - 预测历史（按设备查看历史预测记录）
 */
import React, { useState } from 'react';
import { Tabs } from 'antd';
import {
  DashboardOutlined,
  ThunderboltOutlined,
  ApiOutlined,
  HistoryOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import Dashboard from './Dashboard';
import Prediction from './Prediction';
import Model from './Model';
import History from './History';

const PredictiveMaintenancePage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('dashboard');

  return (
    <div style={{ padding: 0 }}>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        style={{ background: '#fff', padding: '0 16px', borderRadius: 8 }}
        items={[
          {
            key: 'dashboard',
            label: (
              <span>
                <DashboardOutlined />
                仪表盘
              </span>
            ),
            children: <Dashboard />,
          },
          {
            key: 'prediction',
            label: (
              <span>
                <ThunderboltOutlined />
                设备预测
              </span>
            ),
            children: <Prediction />,
          },
          {
            key: 'model',
            label: (
              <span>
                <ApiOutlined />
                模型管理
              </span>
            ),
            children: <Model />,
          },
          {
            key: 'history',
            label: (
              <span>
                <HistoryOutlined />
                预测历史
              </span>
            ),
            children: <History />,
          },
        ]}
      />
    </div>
  );
};

export default PredictiveMaintenancePage;