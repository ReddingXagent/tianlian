/**
 * 天链 V3 - 知识库：统计卡片
 */
import React from 'react';
import { Row, Col, Card, Statistic } from 'antd';
import { FileTextOutlined, TagOutlined } from '@ant-design/icons';
import type { StatsData } from '../types';

const StatsCards: React.FC<{ stats: StatsData }> = ({ stats }) => (
  <Row gutter={16} style={{ marginBottom: 16 }}>
    <Col span={6}>
      <Card size="small">
        <Statistic title="文章总数" value={stats.total} prefix={<FileTextOutlined />} />
      </Card>
    </Col>
    <Col span={6}>
      <Card size="small">
        <Statistic title="分类数" value={stats.categories} prefix={<TagOutlined />} />
      </Card>
    </Col>
    <Col span={6}>
      <Card size="small">
        <Statistic title="总浏览量" value={stats.total_views} />
      </Card>
    </Col>
    <Col span={6}>
      <Card size="small">
        <Statistic title="最多分类" value={stats.top_category} />
      </Card>
    </Col>
  </Row>
);

export default StatsCards;
