/**
 * 天链 V3 - Dashboard 系统健康状态面板
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Row, Col, Statistic, Tag, Space, Typography } from 'antd';
import { HeartOutlined, WarningOutlined, AlertOutlined } from '@ant-design/icons';
import type { HealthData } from '../types';

const { Text } = Typography;

const HealthPanel: React.FC<{ healthData: HealthData | null }> = ({ healthData }) => {
  const { t } = useTranslation();
  if (!healthData) return null;

  return (
    <Card
      title={
        <Space>
          <HeartOutlined style={{ color: '#52c41a' }} />
          <Text style={{ color: 'var(--text-primary)' }}>{t('dashboard.system_health')}</Text>
        </Space>
      }
      className="dash-card"
      extra={<Tag color={healthData.avg_health_score >= 90 ? 'green' : healthData.avg_health_score >= 70 ? 'orange' : 'red'}>
        {t('dashboard.health_score_avg')}: {healthData.avg_health_score}{t('dashboard.score_unit')}
      </Tag>}
    >
      <Row gutter={[12, 12]}>
        <Col span={12}>
          <Statistic
            title={t('dashboard.healthy_devices')}
            value={healthData.healthy_devices}
            suffix={`/ ${healthData.total_devices}${t('dashboard.device_units')}`}
            valueStyle={{ color: '#52c41a', fontSize: 18 }}
          />
        </Col>
        <Col span={12}>
          <Statistic
            title={t('dashboard.health_rate')}
            value={healthData.health_rate}
            suffix="%"
            valueStyle={{ color: '#52c41a', fontSize: 18 }}
          />
        </Col>
        <Col span={12}>
          <Statistic
            title={t('dashboard.warning_devices')}
            value={healthData.warning_devices}
            suffix={t('dashboard.device_units')}
            valueStyle={{ color: '#faad14', fontSize: 16 }}
            prefix={<WarningOutlined />}
          />
        </Col>
        <Col span={12}>
          <Statistic
            title={t('dashboard.fault_devices')}
            value={healthData.critical_devices}
            suffix={t('dashboard.device_units')}
            valueStyle={{ color: '#ff4d4f', fontSize: 16 }}
            prefix={<AlertOutlined />}
          />
        </Col>
      </Row>
    </Card>
  );
};

export default HealthPanel;
