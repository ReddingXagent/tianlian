/**
 * 团队统计卡片行（总数 / 启用 / 成员）
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Statistic, Row, Col } from 'antd';
import { TeamOutlined } from '@ant-design/icons';

interface TeamStatsCardsProps {
  stats: { total: number; active: number; totalMembers: number };
}

const TeamStatsCards: React.FC<TeamStatsCardsProps> = ({ stats }) => {
  const { t } = useTranslation();
  return (
    <Row gutter={16} style={{ marginBottom: 16 }}>
      <Col span={8}>
        <Card size="small">
          <Statistic title={t('pages.teams.total_count')} value={stats.total} prefix={<TeamOutlined />} />
        </Card>
      </Col>
      <Col span={8}>
        <Card size="small">
          <Statistic title={t('pages.teams.active_count')} value={stats.active} valueStyle={{ color: '#34a853' }} />
        </Card>
      </Col>
      <Col span={8}>
        <Card size="small">
          <Statistic title={t('pages.teams.total_members')} value={stats.totalMembers} valueStyle={{ color: '#ff5a36' }} />
        </Card>
      </Col>
    </Row>
  );
};

export default TeamStatsCards;
