/**
 * 天链 V3 - Dashboard 统计卡片
 */
import React from 'react';
import { Row, Col, Card, Statistic, Tag, Space, Typography } from 'antd';
import {
  EnvironmentOutlined, ApiOutlined, CheckCircleOutlined, AlertOutlined,
} from '@ant-design/icons';
import type { StatsOverview } from '../../../types';

const { Text } = Typography;

const StatCards: React.FC<{ overviewStats: StatsOverview | null }> = ({ overviewStats }) => {
  if (!overviewStats) return null;

  const cards = [
    {
      key: 'stations',
      title: '站点总数',
      value: overviewStats.stations.total,
      suffix: '个',
      prefix: <EnvironmentOutlined />,
      valueColor: 'var(--primary-color)',
      tags: [
        { color: 'green', text: `在线 ${overviewStats.stations.online}` },
        { color: 'red', text: `离线 ${overviewStats.stations.offline}` },
      ],
    },
    {
      key: 'devices',
      title: '设备总数',
      value: overviewStats.devices.total,
      suffix: '台',
      prefix: <ApiOutlined />,
      valueColor: 'var(--primary-color)',
      tags: [
        { color: 'green', text: `在线 ${overviewStats.devices.online}` },
        { color: 'red', text: `故障 ${overviewStats.devices.fault}` },
      ],
    },
    {
      key: 'online-rate',
      title: '设备在线率',
      value: overviewStats.devices.online_rate,
      suffix: '%',
      prefix: <CheckCircleOutlined />,
      valueColor: '#52c41a',
      subtitle: `健康度平均: ${overviewStats.health.average}分`,
    },
    {
      key: 'alarms',
      title: '活跃告警',
      value: overviewStats.alarms.active,
      suffix: '个',
      prefix: <AlertOutlined />,
      valueColor: '#ff4d4f',
      tags: [
        { color: 'red', text: `严重 ${overviewStats.alarms.critical}` },
        { color: 'orange', text: `主要 ${overviewStats.alarms.major}` },
      ],
    },
  ];

  return (
    <Row gutter={[16, 16]}>
      {cards.map((card, idx) => (
        <Col xs={12} sm={12} md={6} key={card.key}>
          <Card
            className={`dash-stat-card card-reveal ${idx < 4 ? `card-reveal-delay-${idx + 1}` : ''}`}
          >
            <Statistic
              title={card.title}
              value={card.value}
              suffix={card.suffix}
              prefix={card.prefix}
              valueStyle={{ color: card.valueColor }}
            />
            <div style={{ marginTop: 8 }}>
              {card.tags ? (
                <Space>
                  {card.tags.map((tag, ti) => (
                    <Tag key={ti} color={tag.color}>{tag.text}</Tag>
                  ))}
                </Space>
              ) : (
                <Text style={{ color: 'var(--text-secondary)' }}>{card.subtitle}</Text>
              )}
            </div>
          </Card>
        </Col>
      ))}
    </Row>
  );
};

export default StatCards;
