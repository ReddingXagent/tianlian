/**
 * 工单统计卡片行
 */
import React from 'react';
import { Card, Statistic, Row, Col } from 'antd';
import {
  FileTextOutlined, ClockCircleOutlined, UserOutlined,
  ThunderboltOutlined, CheckCircleOutlined, ExclamationCircleOutlined,
} from '@ant-design/icons';

interface StatsCardsProps {
  stats: {
    total: number;
    pending: number;
    accepted: number;
    processing: number;
    completed: number;
    urgent: number;
  };
}

const StatsCards: React.FC<StatsCardsProps> = ({ stats }) => (
  <Row gutter={16} style={{ marginBottom: 16 }}>
    <Col span={4}>
      <Card size="small">
        <Statistic title="总工单" value={stats.total} prefix={<FileTextOutlined />} />
      </Card>
    </Col>
    <Col span={4}>
      <Card size="small">
        <Statistic title="待派单" value={stats.pending} valueStyle={{ color: '#f5a623' }} prefix={<ClockCircleOutlined />} />
      </Card>
    </Col>
    <Col span={4}>
      <Card size="small">
        <Statistic title="已接单" value={stats.accepted} valueStyle={{ color: '#ff5a36' }} prefix={<UserOutlined />} />
      </Card>
    </Col>
    <Col span={4}>
      <Card size="small">
        <Statistic title="处理中" value={stats.processing} valueStyle={{ color: '#ff5a36' }} prefix={<ThunderboltOutlined />} />
      </Card>
    </Col>
    <Col span={4}>
      <Card size="small">
        <Statistic title="已完成" value={stats.completed} valueStyle={{ color: '#34a853' }} prefix={<CheckCircleOutlined />} />
      </Card>
    </Col>
    <Col span={4}>
      <Card size="small">
        <Statistic title="紧急未结" value={stats.urgent} valueStyle={{ color: stats.urgent > 0 ? '#ea4335' : '#34a853' }} prefix={<ExclamationCircleOutlined />} />
      </Card>
    </Col>
  </Row>
);

export default StatsCards;
