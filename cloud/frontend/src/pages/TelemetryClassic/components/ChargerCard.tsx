/**
 * 充电桩数据卡片
 */
import React from 'react';
import { Card, Row, Col, Statistic, Progress, Tag, Typography } from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
import type { TelemetryData } from '../types';

const { Text } = Typography;

const ChargerCard: React.FC<{ telemetry: TelemetryData | null }> = ({ telemetry }) => (
  <Card title={<><ThunderboltOutlined /> 充电桩数据</>} style={{ marginBottom: 16 }}>
    <Row gutter={[16, 16]}>
      <Col span={6}>
        <Statistic
          title="输出电压"
          value={telemetry?.charger_voltage || 0}
          suffix="V"
          precision={1}
        />
      </Col>
      <Col span={6}>
        <Statistic
          title="输出电流"
          value={telemetry?.charger_current || 0}
          suffix="A"
          precision={2}
        />
      </Col>
      <Col span={6}>
        <Statistic
          title="输出功率"
          value={telemetry?.charger_power || 0}
          suffix="kW"
          precision={2}
          valueStyle={{ color: '#3f8600' }}
        />
      </Col>
      <Col span={6}>
        <Statistic
          title="枪头温度"
          value={telemetry?.gun_temperature || 0}
          suffix="℃"
          precision={1}
        />
      </Col>
      <Col span={12}>
        <div style={{ marginBottom: 8 }}>
          <Text strong>车辆SOC</Text>
        </div>
        <Progress
          percent={telemetry?.charger_soc || 0}
          strokeColor="#3f8600"
          format={(percent) => `${percent?.toFixed(0)}%`}
        />
      </Col>
      <Col span={12}>
        <div style={{ marginBottom: 8 }}>
          <Text strong>枪状态</Text>
        </div>
        <Tag color={
          telemetry?.gun_status === 0 ? 'default' :
          telemetry?.gun_status === 1 ? 'green' :
          'red'
        }>
          {telemetry?.gun_status === 0 ? '空闲' :
           telemetry?.gun_status === 1 ? '充电中' :
           '故障'}
        </Tag>
      </Col>
    </Row>
  </Card>
);

export default ChargerCard;
