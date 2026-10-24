/**
 * 智能日志分析页面
 */
import React, { useState, useEffect } from 'react';
import {
  Card, Table, Button, Modal, Form, Input, Select, Tag, Space, message,
  Tabs, Row, Col, Statistic, Descriptions, Progress, Alert, Spin
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  FileSearchOutlined, RobotOutlined, SettingOutlined,
  HistoryOutlined, ThunderboltOutlined, LineChartOutlined
} from '@ant-design/icons';
import api from '../../api';

const { TextArea } = Input;

interface DiagnosisRecord {
  id: number;
  device_id: number;
  station_id?: number;
  status: string;
  trigger_type: string;
  log_source: string;
  fault_type?: string;
  fault_location?: string;
  root_cause?: string;
  severity?: string;
  confidence?: number;
  immediate_actions?: string;
  repair_suggestions?: string;
  preventive_measures?: string;
  remote_fixable?: boolean;
  duration_ms?: number;
  created_at: string;
  completed_at?: string;
}

interface ModelConfig {
  providers: any[];
  task_mappings: Record<string, string>;
}

const LogAnalysisPage: React.FC = () => {
  const [history, setHistory] = useState<DiagnosisRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [analyzeModalVisible, setAnalyzeModalVisible] = useState(false);
  const [configModalVisible, setConfigModalVisible] = useState(false);
  const [resultModalVisible, setResultModalVisible] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  const [modelConfig, setModelConfig] = useState<ModelConfig | null>(null);
  const [devices, setDevices] = useState<any[]>([]);
  const [form] = Form.useForm();
  const [configForm] = Form.useForm();

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const res = await api.get('/log-analysis', { params: { page: 1, page_size: 50 } });
      const data = res.data as any;
      setHistory(data.items || data || []);
    } catch (error) {
      message.error('获取诊断历史失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchDevices = async () => {
    try {
      const res = await api.get('/devices');
      const data = res.data as any;
      setDevices(data.items || data || []);
    } catch (error) {
      // ignore
    }
  };

  const fetchModelConfig = async () => {
    try {
      const res = await api.get('/log-analysis/model_config');
      setModelConfig(res.data as any);
    } catch (error) {
      message.error('获取模型配置失败');
    }
  };

  useEffect(() => {
    fetchHistory();
    fetchDevices();
    fetchModelConfig();
  }, []);

  const handleAnalyze = async (values: any) => {
    setAnalyzing(true);
    try {
      const res = await api.post('/log-analysis/analyze', {
        device_id: values.device_id,
        logs: values.logs.split('\n').filter(l => l.trim()),
        fault_code: values.fault_code,
        fault_description: values.fault_description,
      });
      const data = res.data as any;
      setAnalysisResult(data);
      setAnalyzeModalVisible(false);
      setResultModalVisible(true);
      form.resetFields();
      fetchHistory();
      message.success('分析完成');
    } catch (error: any) {
      message.error(error.response?.data?.message || '分析失败');
    } finally {
      setAnalyzing(false);
    }
  };

  const handleTriggerAlarmDiagnosis = async (alarmId: number) => {
    try {
      const res = await api.post(`/log-analysis/trigger/${alarmId}`);
      message.success('诊断已触发');
      fetchHistory();
    } catch (error) {
      message.error('触发诊断失败');
    }
  };

  const handleUpdateModelConfig = async (values: any) => {
    try {
      await api.post('/log-analysis/model_config', values.providers);
      message.success('模型配置已更新');
      setConfigModalVisible(false);
      fetchModelConfig();
    } catch (error) {
      message.error('更新配置失败');
    }
  };

  const getStatusTag = (status: string) => {
    const map: Record<string, { color: string; text: string }> = {
      pending: { color: 'blue', text: '待分析' },
      running: { color: 'orange', text: '分析中' },
      completed: { color: 'green', text: '已完成' },
      failed: { color: 'red', text: '失败' },
    };
    return map[status] || { color: 'default', text: status };
  };

  const getSeverityTag = (severity?: string) => {
    if (!severity) return null;
    const map: Record<string, string> = {
      low: 'green', medium: 'orange', high: 'red', critical: 'magenta',
    };
    return <Tag color={map[severity] || 'default'}>{severity}</Tag>;
  };

  const columns: ColumnsType<DiagnosisRecord> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '设备ID', dataIndex: 'device_id', width: 80 },
    { title: '触发方式', dataIndex: 'trigger_type', width: 100, render: (v: string) => <Tag>{v}</Tag> },
    { title: '日志来源', dataIndex: 'log_source', width: 120 },
    { title: '故障类型', dataIndex: 'fault_type', width: 150 },
    { title: '故障位置', dataIndex: 'fault_location', width: 150 },
    { title: '严重程度', dataIndex: 'severity', width: 100, render: getSeverityTag },
    { title: '置信度', dataIndex: 'confidence', width: 100, render: (v?: number) => v ? <Progress percent={Math.round(v * 100)} size="small" /> : '-' },
    { title: '耗时', dataIndex: 'duration_ms', width: 100, render: (v?: number) => v ? `${v}ms` : '-' },
    { title: '状态', dataIndex: 'status', width: 100, render: (v: string) => {
      const t = getStatusTag(v);
      return <Tag color={t.color}>{t.text}</Tag>;
    }},
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: (v: string) => v?.slice(0, 19) },
    { title: '操作', width: 100, fixed: 'right', render: (_: any, r: DiagnosisRecord) => (
      <Button size="small" icon={<FileSearchOutlined />} onClick={() => {
        setAnalysisResult(r);
        setResultModalVisible(true);
      }}>详情</Button>
    )},
  ];

  return (
    <Card title={<><RobotOutlined /> 智能日志分析</>} extra={
      <Space>
        <Button icon={<SettingOutlined />} onClick={() => setConfigModalVisible(true)}>模型配置</Button>
        <Button type="primary" icon={<FileSearchOutlined />} onClick={() => setAnalyzeModalVisible(true)}>手动分析</Button>
      </Space>
    }>
      <Tabs items={[
        {
          key: 'history',
          label: <><HistoryOutlined /> 诊断历史</>,
          children: (
            <>
              <Row gutter={16} style={{ marginBottom: 16 }}>
                <Col span={4}><Statistic title="总诊断" value={history.length} /></Col>
                <Col span={4}><Statistic title="已完成" value={history.filter(h => h.status === 'completed').length} /></Col>
                <Col span={4}><Statistic title="失败" value={history.filter(h => h.status === 'failed').length} /></Col>
                <Col span={4}><Statistic title="平均置信度" value={history.filter(h => h.confidence).reduce((a, b) => a + (b.confidence || 0), 0) / history.filter(h => h.confidence).length * 100 || 0} suffix="%" /></Col>
              </Row>
              <Table dataSource={history} columns={columns} rowKey="id" loading={loading} scroll={{ x: 1300 }} />
            </>
          ),
        },
        {
          key: 'config',
          label: <><SettingOutlined /> AI模型配置</>,
          children: modelConfig ? (
            <Card size="small">
              <Descriptions bordered column={1}>
                <Descriptions.Item label="任务-模型映射">
                  <Space direction="vertical">
                    {Object.entries(modelConfig.task_mappings || {}).map(([task, model]) => (
                      <Tag key={task}>{task} → {model}</Tag>
                    ))}
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="Provider数量">{modelConfig.providers?.length || 0}</Descriptions.Item>
              </Descriptions>
            </Card>
          ) : <Spin />,
        },
      ]} />

      {/* 手动分析弹窗 */}
      <Modal title="手动日志分析" open={analyzeModalVisible} onCancel={() => setAnalyzeModalVisible(false)} footer={null} width={700}>
        <Form form={form} onFinish={handleAnalyze} layout="vertical">
          <Form.Item name="device_id" label="设备" rules={[{ required: true }]}>
            <Select placeholder="选择设备" options={devices.map(d => ({ label: d.name || `设备${d.id}`, value: d.id }))} showSearch />
          </Form.Item>
          <Form.Item name="logs" label="日志内容" rules={[{ required: true }]}>
            <TextArea rows={10} placeholder="粘贴日志内容，每行一条" />
          </Form.Item>
          <Form.Item name="fault_code" label="故障代码">
            <Input placeholder="如：E001" />
          </Form.Item>
          <Form.Item name="fault_description" label="故障描述">
            <TextArea rows={2} placeholder="故障现象描述" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={analyzing}>
              <RobotOutlined /> 开始AI分析
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 分析结果弹窗 */}
      <Modal title="诊断结果" open={resultModalVisible} onCancel={() => setResultModalVisible(false)} width={800} footer={null}>
        {analysisResult && (
          <>
            <Alert type={analysisResult.error ? 'error' : 'success'} message={analysisResult.error || '分析完成'} style={{ marginBottom: 16 }} />
            {analysisResult.analysis && (
              <Descriptions bordered column={2}>
                <Descriptions.Item label="故障类型">{analysisResult.analysis.fault_type}</Descriptions.Item>
                <Descriptions.Item label="故障位置">{analysisResult.analysis.fault_location}</Descriptions.Item>
                <Descriptions.Item label="根本原因">{analysisResult.analysis.root_cause}</Descriptions.Item>
                <Descriptions.Item label="严重程度">{getSeverityTag(analysisResult.analysis.severity)}</Descriptions.Item>
                <Descriptions.Item label="置信度"><Progress percent={Math.round((analysisResult.analysis.confidence || 0) * 100)} /></Descriptions.Item>
                <Descriptions.Item label="可远程修复">{analysisResult.analysis.remote_fixable ? <Tag color="green">是</Tag> : <Tag color="red">否</Tag>}</Descriptions.Item>
                <Descriptions.Item label="立即行动" span={2}>{analysisResult.analysis.immediate_actions}</Descriptions.Item>
                <Descriptions.Item label="维修建议" span={2}>{analysisResult.analysis.repair_suggestions}</Descriptions.Item>
                <Descriptions.Item label="预防措施" span={2}>{analysisResult.analysis.preventive_measures}</Descriptions.Item>
              </Descriptions>
            )}
            {analysisResult.model_used && (
              <Card size="small" style={{ marginTop: 16 }}>
                <Space>
                  <LineChartOutlined />
                  <span>使用模型: {analysisResult.model_used}</span>
                  <span>耗时: {analysisResult.duration_ms}ms</span>
                </Space>
              </Card>
            )}
          </>
        )}
      </Modal>

      {/* 模型配置弹窗 */}
      <Modal title="AI模型配置" open={configModalVisible} onCancel={() => setConfigModalVisible(false)} footer={null} width={600}>
        <Form form={configForm} onFinish={handleUpdateModelConfig} layout="vertical">
          <Form.Item label="当前配置">
            <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 4 }}>{JSON.stringify(modelConfig, null, 2)}</pre>
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>保存配置</Button>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

export default LogAnalysisPage;