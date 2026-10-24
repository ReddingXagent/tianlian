/**
 * 电网侧数据卡片
 */
import React from 'react';
import { Card, Row, Col, Statistic } from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
import type { TelemetryData } from '../types';

const GridCard: React.FC<{ telemetry: TelemetryData | null }> = ({ telemetry }) => (
  <Card title={<><ThunderboltOutlined /> 电网侧数据</>} style={{ marginBottom: 16 }}>
    <Row gutter={[16, 16]}>
      <Col span={8}>
        <Statistic
          title="A相电压"
          value={telemetry?.grid_voltage_a || 0}
          suffix="V"
          precision={1}
        />
      </Col>
      <Col span={8}>
        <Statistic
          title="B相电压"
          value={telemetry?.grid_voltage_b || 0}
          suffix="V"
          precision={1}
        />
      </Col>
      <Col span={8}>
        <Statistic
          title="C相电压"
          value={telemetry?.grid_voltage_c || 0}
          suffix="V"
          precision={1}
        />
      </Col>
      <Col span={8}>
        <Statistic
          title="频率"
          value={telemetry?.grid_frequency || 50}
          suffix="Hz"
          precision={2}
        />
      </Col>
      <Col span={8}>
        <Statistic
          title="总功率"
          value={telemetry?.grid_power_total || 0}
          suffix="kW"
          precision={2}
          valueStyle={{ color: '#3f8600' }}
        />
      </Col>
      <Col span={8}>
        <Statistic
          title="功率因数"
          value={telemetry?.grid_power_factor || 0}
          precision={2}
        />
      </Col>
    </Row>
  </Card>
);

export default GridCard;
