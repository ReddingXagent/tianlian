/**
 * 手动日志分析 Tab — 设备选择 + 日志输入 + AI 诊断 + 结果展示
 */
import React, { useState, useEffect } from 'react';
import {
  Card, Button, Input, Select, Space, Spin, Typography, message,
} from 'antd';
import { FileTextOutlined, RobotOutlined } from '@ant-design/icons';
import { deviceAPI, logAnalysisAPI, fetchAllPages } from '../../../api';
import DiagnosisResultCard from './DiagnosisResultCard';

const { TextArea } = Input;
const { Text } = Typography;

function ManualLogAnalysis() {
  const [deviceId, setDeviceId] = useState<number | null>(null);
  const [logs, setLogs] = useState('');
  const [devices, setDevices] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    // 卡 971f853e: page_size 恰 100 上限会静默截断 → fetchAllPages 循环拉全量
    fetchAllPages<any>((params) => deviceAPI.list(params))
      .then((items) => setDevices(items))
      .catch(() => message.error('设备列表加载失败，请刷新重试'));
  }, []);

  const handleAnalyze = async () => {
    if (!deviceId || !logs.trim()) {
      message.warning('请选择设备并输入日志');
      return;
    }
    setLoading(true);
    try {
      const data = (await logAnalysisAPI.analyze({
        device_id: deviceId,
        logs: logs.trim().split('\n'),
      })).data;
      if (data.analysis) {
        setResult(data);
        message.success('诊断完成');
      } else {
        message.error(data.error || '诊断失败');
      }
    } catch (e: any) {
      message.error('请求失败: ' + e.message);
    }
    setLoading(false);
  };

  return (
    <div>
      <Card title={<><FileTextOutlined /> 输入设备日志</>} style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Select
            showSearch
            placeholder="选择设备"
            style={{ width: 300 }}
            onChange={(v) => setDeviceId(v)}
            optionFilterProp="children"
          >
            {devices.map((d: any) => (
              <Select.Option key={d.id} value={d.id}>
                [{d.type || d.device_type}] {d.name} ({d.sn})
              </Select.Option>
            ))}
          </Select>

          <TextArea
            rows={10}
            placeholder={`粘贴设备日志内容，每行一条...\n\n示例:\n[2026-05-10 14:30:00] [WARN] A相电压异常: 265.3V\n[2026-05-10 14:30:01] [ERROR] 电网一段过压保护触发`}
            value={logs}
            onChange={(e) => setLogs(e.target.value)}
          />

          <Space>
            <Button
              type="primary"
              icon={<RobotOutlined />}
              loading={loading}
              onClick={handleAnalyze}
            >
              AI 诊断分析
            </Button>
            <Button onClick={() => {
              setLogs('');
              setResult(null);
            }}>清空</Button>
          </Space>
        </Space>
      </Card>

      {/* 分析结果 */}
      {loading && (
        <Card>
          <Spin tip="AI正在诊断...">
            <div style={{ padding: 50, textAlign: 'center' }}>
              <RobotOutlined style={{ fontSize: 48, color: '#ff5a36' }} />
              <p style={{ marginTop: 16 }}>正在分析日志，请稍候...</p>
            </div>
          </Spin>
        </Card>
      )}

      {result?.analysis && !loading && (
        <DiagnosisResultCard result={result.analysis} record={result} />
      )}
    </div>
  );
}

export default ManualLogAnalysis;
