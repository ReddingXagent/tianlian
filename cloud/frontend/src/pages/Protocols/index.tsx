/**
 * 天链V3 - 协议管理首页（Tabs布局）
 * 整合网关实例CRUD、解析器配置、连接状态仪表板
 */
import React from 'react';
import { Card, Tag, Tabs, Row, Col, Statistic } from 'antd';
import { ApiOutlined, SettingOutlined, DashboardOutlined } from '@ant-design/icons';
import GatewayInstanceList from './GatewayInstanceList';
import ParserConfig from './ParserConfig';
import ConnectionDashboard from './ConnectionDashboard';

const tabItems = [
  {
    key: 'instances',
    label: <span><ApiOutlined /> 网关实例</span>,
    children: <GatewayInstanceList />,
  },
  {
    key: 'parsers',
    label: <span><SettingOutlined /> 解析器配置</span>,
    children: <ParserConfig />,
  },
  {
    key: 'dashboard',
    label: <span><DashboardOutlined /> 连接仪表板</span>,
    children: <ConnectionDashboard />,
  },
];

const ProtocolsPage: React.FC = () => {
  return (
    <div style={{ padding: 24 }}>
      <Card title="协议管理" extra={<Tag color="blue">Phase33</Tag>}>
        <Tabs defaultActiveKey="instances" items={tabItems} />
      </Card>
    </div>
  );
};

export default ProtocolsPage;