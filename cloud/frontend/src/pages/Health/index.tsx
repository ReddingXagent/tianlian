/**
 * 健康度管理页面
 * 核心功能：设备健康评分、健康排名(最佳/最差 Top10)、健康评估、异常设备
 *
 * 数据来源: GET /api/v1/health/devices 聚合端点
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Card, Row, Col, Table, Button, Tag, Space, Progress, Statistic, Tabs, Modal, Descriptions, List, Badge, Tooltip, Empty, message } from 'antd';
import {
  HeartOutlined, WarningOutlined, CheckCircleOutlined,
  MinusOutlined,
  EyeOutlined, ReloadOutlined, AlertOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { healthAPI } from '../../api';

const { TabPane } = Tabs;

// ============ 类型 ============

interface OverallHealth {
  totalDevices: number;
  healthyCount: number;
  warningCount: number;
  criticalCount: number;
  pendingEval: number;
  overallScore: number;
}

interface RankingItem {
  id: number;
  deviceName: string;
  code?: string | null;
  type?: string | null;
  stationName: string;
  score: number;
  status: string;
}

interface EvaluationItem {
  id: number;
  deviceId: number;
  deviceName: string;
  stationName: string;
  score: number;
  evaluator: string;
  evalDate: string;
  issues: string[];
  status: string;
}

interface AbnormalItem {
  id: number;
  deviceName: string;
  stationName: string;
  score: number;
  abnormalIndicators: string[];
  suggestion: string;
}

const DEFAULT_OVERALL: OverallHealth = {
  totalDevices: 0,
  healthyCount: 0,
  warningCount: 0,
  criticalCount: 0,
  pendingEval: 0,
  overallScore: 0,
};

// ============ 主组件 ============

const HealthPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [detailVisible, setDetailVisible] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<EvaluationItem | null>(null);
  const [activeTab, setActiveTab] = useState('1');

  const [healthOverall, setHealthOverall] = useState<OverallHealth>(DEFAULT_OVERALL);
  const [deviceRankings, setDeviceRankings] = useState<{ best: RankingItem[]; worst: RankingItem[] }>({ best: [], worst: [] });
  const [healthEvaluations, setHealthEvaluations] = useState<EvaluationItem[]>([]);
  const [abnormalDevices, setAbnormalDevices] = useState<AbnormalItem[]>([]);

  const fetchHealthData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await healthAPI.list();
      const data = (res.data ?? {}) as {
        overall?: OverallHealth;
        rankings?: { best: RankingItem[]; worst: RankingItem[] };
        evaluations?: EvaluationItem[];
        abnormal?: AbnormalItem[];
      };
      setHealthOverall(data.overall ?? DEFAULT_OVERALL);
      setDeviceRankings(data.rankings ?? { best: [], worst: [] });
      setHealthEvaluations(data.evaluations ?? []);
      setAbnormalDevices(data.abnormal ?? []);
    } catch {
      message.error('获取健康数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealthData();
  }, [fetchHealthData]);

  // ============ 辅助函数 ============

  const getScoreColor = (score: number) => {
    if (score >= 90) return '#52c41a';
    if (score >= 60) return '#faad14';
    return '#ff4d4f';
  };

  const getStatusTag = (status: string) => {
    const map: Record<string, { color: string; text: string }> = {
      normal: { color: 'green', text: '正常' },
      warning: { color: 'orange', text: '告警' },
      critical: { color: 'red', text: '严重' },
    };
    return map[status] || { color: 'default', text: status };
  };

  // ============ 表格列定义 ============

  const rankColumns: ColumnsType<RankingItem> = [
    {
      title: '排名',
      key: 'rank',
      width: 60,
      render: (_: unknown, __: unknown, index: number) => (
        <Badge
          count={index + 1}
          style={{ backgroundColor: index < 3 ? '#1890ff' : '#8c8c8c', fontWeight: 'bold' }}
        />
      ),
    },
    { title: '设备名称', dataIndex: 'deviceName', key: 'deviceName' },
    { title: '所属站点', dataIndex: 'stationName', key: 'stationName', render: (v: string) => v || '-' },
    { title: '类型', dataIndex: 'type', key: 'type', render: (v: string) => v || '-', width: 120 },
    {
      title: '健康分',
      dataIndex: 'score',
      key: 'score',
      align: 'center',
      render: (score: number) => (
        <Progress
          type="circle"
          percent={score}
          width={50}
          strokeColor={getScoreColor(score)}
          format={percent => `${percent?.toFixed(1)}`}
        />
      ),
    },
  ];

  const evaluationColumns: ColumnsType<EvaluationItem> = [
    { title: '设备名称', dataIndex: 'deviceName', key: 'deviceName' },
    { title: '所属站点', dataIndex: 'stationName', key: 'stationName', render: (v: string) => v || '-' },
    {
      title: '健康评分',
      dataIndex: 'score',
      key: 'score',
      align: 'center',
      render: (score: number) => (
        <Progress
          type="circle"
          percent={score}
          width={45}
          strokeColor={getScoreColor(score)}
          format={percent => `${percent}`}
        />
      ),
    },
    { title: '评估时间', dataIndex: 'evalDate', key: 'evalDate', width: 160, render: (v: string) => v || '-' },
    { title: '评估人', dataIndex: 'evaluator', key: 'evaluator', align: 'center', render: (v: string) => v || '-' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      align: 'center',
      render: (status: string) => {
        const tag = getStatusTag(status);
        return <Tag color={tag.color}>{tag.text}</Tag>;
      },
    },
    {
      title: '操作',
      key: 'action',
      align: 'center',
      render: (_: unknown, record: EvaluationItem) => (
        <Button
          type="link"
          icon={<EyeOutlined />}
          onClick={() => {
            setSelectedRecord(record);
            setDetailVisible(true);
          }}
        >
          查看详情
        </Button>
      ),
    },
  ];

  const abnormalColumns: ColumnsType<AbnormalItem> = [
    { title: '设备名称', dataIndex: 'deviceName', key: 'deviceName' },
    { title: '所属站点', dataIndex: 'stationName', key: 'stationName', render: (v: string) => v || '-' },
    {
      title: '健康分',
      dataIndex: 'score',
      key: 'score',
      align: 'center',
      render: (score: number) => (
        <span style={{ color: getScoreColor(score), fontWeight: 'bold', fontSize: 16 }}>
          {score}
        </span>
      ),
    },
    {
      title: '异常指标',
      dataIndex: 'abnormalIndicators',
      key: 'abnormalIndicators',
      render: (indicators: string[]) =>
        indicators && indicators.length ? (
          <Space wrap>
            {indicators.map((item, idx) => (
              <Tag key={idx} color="error">{item}</Tag>
            ))}
          </Space>
        ) : (
          <span style={{ color: '#999' }}>-</span>
        ),
    },
    {
      title: '建议措施',
      dataIndex: 'suggestion',
      key: 'suggestion',
      width: 300,
      render: (text: string) =>
        text ? (
          <Tooltip title={text}>
            <span style={{
              maxWidth: 280,
              display: 'inline-block',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {text}
            </span>
          </Tooltip>
        ) : (
          <span style={{ color: '#999' }}>-</span>
        ),
    },
  ];

  // ============ 渲染 ============

  return (
    <div>
      {/* 顶部概览 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={4}>
          <Card>
            <Statistic title="总设备数" value={healthOverall.totalDevices} prefix={<HeartOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <Card>
            <Statistic title="健康设备" value={healthOverall.healthyCount} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <Card>
            <Statistic title="告警设备" value={healthOverall.warningCount} prefix={<WarningOutlined />} valueStyle={{ color: '#faad14' }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <Card>
            <Statistic title="严重异常" value={healthOverall.criticalCount} prefix={<AlertOutlined />} valueStyle={{ color: '#ff4d4f' }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <Card>
            <Statistic title="待评估" value={healthOverall.pendingEval} prefix={<MinusOutlined />} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <Card style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: '#fff' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 14, opacity: 0.9 }}>整体健康分</div>
              <Progress
                type="circle"
                percent={healthOverall.overallScore}
                width={80}
                strokeColor="#fff"
                trailColor="rgba(255,255,255,0.2)"
                format={percent => (
                  <span style={{ color: '#fff', fontSize: 24, fontWeight: 'bold' }}>
                    {percent?.toFixed(1)}
                  </span>
                )}
              />
            </div>
          </Card>
        </Col>
      </Row>

      {/* Tab 内容 */}
      <Card>
        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          <TabPane tab="设备健康榜" key="1">
            <div style={{ marginBottom: 16 }}>
              <Button icon={<ReloadOutlined />} onClick={fetchHealthData} loading={loading}>
                刷新数据
              </Button>
            </div>
            {deviceRankings.best.length === 0 && deviceRankings.worst.length === 0 ? (
              <Empty description="暂无设备健康数据" />
            ) : (
              <>
                <h4 style={{ marginBottom: 12 }}>🏆 健康最佳 Top10</h4>
                <Table columns={rankColumns} dataSource={deviceRankings.best} rowKey="id" loading={loading} pagination={false} size="small" style={{ marginBottom: 24 }} />
                <h4 style={{ marginBottom: 12 }}>⚠️ 需关注 Top10</h4>
                <Table columns={rankColumns} dataSource={deviceRankings.worst} rowKey="id" loading={loading} pagination={false} size="small" />
              </>
            )}
          </TabPane>

          <TabPane tab="健康评估" key="2">
            <div style={{ marginBottom: 16 }}>
              <Button icon={<ReloadOutlined />} onClick={fetchHealthData} loading={loading}>
                刷新数据
              </Button>
            </div>
            <Table
              columns={evaluationColumns}
              dataSource={healthEvaluations}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
              locale={{ emptyText: <Empty description="暂无评估记录" /> }}
            />
          </TabPane>

          <TabPane
            tab={
              <span>
                <AlertOutlined />
                异常设备
                <Badge count={abnormalDevices.length} style={{ marginLeft: 8 }} offset={[10, 0]} />
              </span>
            }
            key="3"
          >
            <div style={{ marginBottom: 16 }}>
              <Button icon={<ReloadOutlined />} onClick={fetchHealthData} loading={loading}>
                刷新数据
              </Button>
            </div>
            <Table
              columns={abnormalColumns}
              dataSource={abnormalDevices}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
              locale={{ emptyText: <Empty description="暂无异常设备" /> }}
              rowClassName={(record) => (record.score < 60 ? 'critical-row' : '')}
            />
          </TabPane>
        </Tabs>
      </Card>

      {/* 评估详情弹窗 */}
      <Modal
        title="健康评估详情"
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDetailVisible(false)}>
            关闭
          </Button>,
        ]}
        width={600}
      >
        {selectedRecord && (
          <div>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="设备名称">{selectedRecord.deviceName}</Descriptions.Item>
              <Descriptions.Item label="所属站点">{selectedRecord.stationName || '-'}</Descriptions.Item>
              <Descriptions.Item label="健康评分">
                <Progress
                  type="circle"
                  percent={selectedRecord.score}
                  width={60}
                  strokeColor={getScoreColor(selectedRecord.score)}
                  format={percent => `${percent}`}
                />
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={getStatusTag(selectedRecord.status).color}>
                  {getStatusTag(selectedRecord.status).text}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="评估人">{selectedRecord.evaluator || '-'}</Descriptions.Item>
              <Descriptions.Item label="评估时间">{selectedRecord.evalDate || '-'}</Descriptions.Item>
            </Descriptions>

            <div style={{ marginTop: 16 }}>
              <h4 style={{ marginBottom: 8 }}>主要问题</h4>
              {selectedRecord.issues && selectedRecord.issues.length ? (
                <List
                  size="small"
                  bordered
                  dataSource={selectedRecord.issues}
                  renderItem={(item: string) => (
                    <List.Item>
                      <WarningOutlined style={{ color: '#faad14', marginRight: 8 }} />
                      {item}
                    </List.Item>
                  )}
                />
              ) : (
                <Empty description="暂无异常记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </div>
          </div>
        )}
      </Modal>

      <style>{`
        .critical-row {
          background-color: #fff1f0;
        }
        .critical-row:hover > td {
          background-color: #ffe7e6 !important;
        }
      `}</style>
    </div>
  );
};

export default HealthPage;
