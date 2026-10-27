/**
 * 电池侧数据卡片
 */
import React from 'react';
import { Card, Row, Col, Statistic, Progress, Typography } from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
import type { TelemetryData } from '../types';

const { Text } = Typography;

const BatteryCard: React.FC<{ telemetry: TelemetryData | null }> = ({ telemetry }) => (
  <Card title={<><ThunderboltOutlined /> 电池侧数据</>} style={{ marginBottom: 16 }}>
    <Row gutter={[16, 16]}>
      <Col span={6}>
        <Statistic
          title="电压"
          value={telemetry?.battery_voltage || 0}
          suffix="V"
          precision={1}
        />
      </Col>
      <Col span={6}>
        <Statistic
          title="电流"
          value={telemetry?.battery_current || 0}
          suffix="A"
          precision={2}
          valueStyle={{
            color: telemetry?.battery_current > 0 ? '#3f8600' : '#cf1322'
          }}
        />
        <Text type="secondary">
          {telemetry?.battery_current > 0 ? '充电' : '放电'}
        </Text>
      </Col>
      <Col span={6}>
        <Statistic
          title="功率"
          value={telemetry?.battery_power || 0}
          suffix="kW"
          precision={2}
        />
      </Col>
      <Col span={6}>
        <Statistic
          title="温度"
          value={telemetry?.battery_temperature || 0}
          suffix="℃"
          precision={1}
        />
      </Col>
      <Col span={12}>
        <div style={{ marginBottom: 8 }}>
          <Text strong>SOC (电池容量)</Text>
        </div>
        <Progress
          percent={telemetry?.battery_soc || 0}
          strokeColor={{
            '0%': '#ea4335',
            '50%': '#f5a623',
            '100%': '#34a853',
          }}
          format={(percent) => `${percent?.toFixed(0)}%`}
        />
      </Col>
      <Col span={12}>
        <div style={{ marginBottom: 8 }}>
          <Text strong>SOH (健康度)</Text>
        </div>
        <Progress
          percent={telemetry?.battery_soh || 0}
          strokeColor="#34a853"
          format={(percent) => `${percent?.toFixed(0)}%`}
        />
      </Col>
    </Row>
  </Card>
);

export default BatteryCard;
