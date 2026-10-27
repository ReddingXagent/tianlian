/**
 * 光伏侧数据卡片
 */
import React from 'react';
import { Card, Row, Col, Statistic } from 'antd';
import { DashboardOutlined } from '@ant-design/icons';
import type { TelemetryData } from '../types';

const PVCard: React.FC<{ telemetry: TelemetryData | null }> = ({ telemetry }) => (
  <Card title={<><DashboardOutlined /> 光伏侧数据</>} style={{ marginBottom: 16 }}>
    <Row gutter={[16, 16]}>
      <Col span={8}>
        <Statistic
          title="PV1电压"
          value={telemetry?.pv1_voltage || 0}
          suffix="V"
          precision={1}
        />
      </Col>
      <Col span={8}>
        <Statistic
          title="PV1电流"
          value={telemetry?.pv1_current || 0}
          suffix="A"
          precision={2}
        />
      </Col>
      <Col span={8}>
        <Statistic
          title="PV1功率"
          value={telemetry?.pv1_power || 0}
          suffix="kW"
          precision={2}
          valueStyle={{ color: '#f5a623' }}
        />
      </Col>
      {telemetry?.pv2_voltage && (
        <>
          <Col span={8}>
            <Statistic
              title="PV2电压"
              value={telemetry?.pv2_voltage}
              suffix="V"
              precision={1}
            />
          </Col>
          <Col span={8}>
            <Statistic
              title="PV2电流"
              value={telemetry?.pv2_current}
              suffix="A"
              precision={2}
            />
          </Col>
          <Col span={8}>
            <Statistic
              title="PV2功率"
              value={telemetry?.pv2_power}
              suffix="kW"
              precision={2}
              valueStyle={{ color: '#f5a623' }}
            />
          </Col>
        </>
      )}
      {telemetry?.pv_power_total && (
        <Col span={24}>
          <Statistic
            title="总发电功率"
            value={telemetry?.pv_power_total}
            suffix="kW"
            precision={2}
            valueStyle={{ color: '#f5a623' }}
          />
        </Col>
      )}
    </Row>
  </Card>
);

export default PVCard;
