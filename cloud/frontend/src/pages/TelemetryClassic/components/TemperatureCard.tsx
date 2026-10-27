/**
 * 温度数据卡片
 */
import React from 'react';
import { Card, Row, Col, Statistic, Tag } from 'antd';
import { AlertOutlined, WarningOutlined } from '@ant-design/icons';
import type { TelemetryData } from '../types';

const TemperatureCard: React.FC<{ telemetry: TelemetryData | null }> = ({ telemetry }) => (
  <Card title={<><AlertOutlined /> 温度数据</>} style={{ marginBottom: 16 }}>
    <Row gutter={[16, 16]}>
      <Col span={12}>
        <Statistic
          title="机内温度"
          value={telemetry?.internal_temperature || 0}
          suffix="℃"
          precision={1}
          valueStyle={{
            color: telemetry?.internal_temperature > 50 ? '#cf1322' : '#3f8600'
          }}
        />
        {telemetry?.internal_temperature > 50 && (
          <Tag color="warning" style={{ marginTop: 8 }}>
            <WarningOutlined /> 温度偏高
          </Tag>
        )}
      </Col>
      <Col span={12}>
        <Statistic
          title="环境温度"
          value={telemetry?.ambient_temperature || 0}
          suffix="℃"
          precision={1}
        />
      </Col>
    </Row>
  </Card>
);

export default TemperatureCard;
