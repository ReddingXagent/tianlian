/**
 * 诊断结果卡片 — 概要 + 根因 + 可能原因/立即处理/维修建议 + 预防措施 + 元信息
 */
import React from 'react';
import { Card, Row, Col, Tag, Space, Typography, Alert, Descriptions } from 'antd';
import {
  BugOutlined, ThunderboltOutlined, MedicineBoxOutlined, SafetyOutlined,
} from '@ant-design/icons';
import { severityColors, severityText } from '../constants';
import type { AIDiagnosisResult } from '../types';

const { Text } = Typography;

interface DiagnosisResultCardProps {
  result: AIDiagnosisResult;
  record?: any;
}

function DiagnosisResultCard({ result, record }: DiagnosisResultCardProps) {
  if (!result) return null;

  return (
    <div>
      {/* 概要 */}
      <Alert
        message={
          <Space>
            <Text strong>{result.fault_type}</Text>
            <Tag color={severityColors[result.severity]}>
              {severityText[result.severity] || result.severity}
            </Tag>
            <Tag color={result.confidence && result.confidence > 0.8 ? 'blue' : 'orange'}>
              置信度: {((result.confidence || 0) * 100).toFixed(0)}%
            </Tag>
            {result.remote_fixable && <Tag color="green">可远程修复</Tag>}
          </Space>
        }
        description={`故障定位: ${result.fault_location}`}
        type={result.severity === 'critical' ? 'error' : 'warning'}
        showIcon
        style={{ marginBottom: 16 }}
      />

      {/* 根因分析 */}
      <Card title={<><BugOutlined /> 根因分析</>} size="small" style={{ marginBottom: 12 }}>
        <Text>{result.root_cause}</Text>
      </Card>

      <Row gutter={12}>
        {/* 可能原因 */}
        <Col span={8}>
          <Card title="可能原因" size="small" style={{ marginBottom: 12, height: '100%' }}>
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {(result.possible_causes || []).map((c, i) => (
                <li key={i}><Text style={{ fontSize: 13 }}>{c}</Text></li>
              ))}
            </ul>
          </Card>
        </Col>

        {/* 立即行动 */}
        <Col span={8}>
          <Card
            title={<><ThunderboltOutlined /> 立即处理</>}
            size="small"
            style={{ marginBottom: 12, height: '100%', borderColor: '#f5a623' }}
          >
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {(result.immediate_actions || []).map((a, i) => (
                <li key={i}><Text style={{ fontSize: 13 }}>{a}</Text></li>
              ))}
            </ul>
          </Card>
        </Col>

        {/* 维修建议 */}
        <Col span={8}>
          <Card
            title={<><MedicineBoxOutlined /> 维修建议</>}
            size="small"
            style={{ marginBottom: 12, height: '100%', borderColor: '#34a853' }}
          >
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {(result.repair_suggestions || []).map((s, i) => (
                <li key={i}><Text style={{ fontSize: 13 }}>{s}</Text></li>
              ))}
            </ul>
          </Card>
        </Col>
      </Row>

      {/* 预防措施 */}
      {(result.preventive_measures || []).length > 0 && (
        <Card
          title={<><SafetyOutlined /> 预防措施</>}
          size="small"
          style={{ marginBottom: 12 }}
        >
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {(result.preventive_measures || []).map((p, i) => (
              <li key={i}><Text style={{ fontSize: 13 }}>{p}</Text></li>
            ))}
          </ul>
        </Card>
      )}

      {/* 元信息 */}
      {record && (
        <Descriptions size="small" column={4} style={{ marginTop: 8 }}>
          <Descriptions.Item label="诊断耗时">{record.duration_ms}ms</Descriptions.Item>
          <Descriptions.Item label="触发方式">
            {record.trigger_type === 'auto' ? '自动触发' : '手动'}
          </Descriptions.Item>
          {record.matched_fault_code && (
            <Descriptions.Item label="匹配故障码">
              <Tag>{record.matched_fault_code} {record.matched_fault_name}</Tag>
            </Descriptions.Item>
          )}
        </Descriptions>
      )}
    </div>
  );
}

export default DiagnosisResultCard;
