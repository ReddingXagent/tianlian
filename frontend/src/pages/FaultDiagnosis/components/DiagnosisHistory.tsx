/**
 * 诊断历史 Tab — 历史记录表格 + 详情弹窗
 */
import React, { useState, useEffect } from 'react';
import {
  Table, Modal, Button, Tag, Space, Typography,
} from 'antd';
import AutoHeightTable from '../../../components/AutoHeightTable';
import { ReloadOutlined, RobotOutlined } from '@ant-design/icons';
import { logAnalysisAPI } from '../../../api';
import { severityColors, severityText, statusColors } from '../constants';
import type { AnalysisRecord } from '../types';
import DiagnosisResultCard from './DiagnosisResultCard';

const { Text } = Typography;

function DiagnosisHistory() {
  const [records, setRecords] = useState<AnalysisRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<AnalysisRecord | null>(null);
  const [resultModal, setResultModal] = useState<any>(null);

  useEffect(() => { loadRecords(); }, []);

  const loadRecords = async () => {
    setLoading(true);
    try {
      const data = await logAnalysisAPI.list({ page_size: 50 });
      setRecords((data.data?.items || []) as AnalysisRecord[]);
    } catch {}
    setLoading(false);
  };

  const viewDetail = async (record: AnalysisRecord) => {
    setSelected(record);
    try {
      const data = await logAnalysisAPI.get(record.id);
      if (data.data) {
        let result = null;
        try {
          result = JSON.parse(data.data.raw_ai_response || '{}');
        } catch {
          try {
            const jsonMatch = (data.data.raw_ai_response || '').match(/\{[\s\S]*\}/);
            result = jsonMatch ? JSON.parse(jsonMatch[0]) : null;
          } catch {}
        }
        setResultModal(result);
      }
    } catch {}
  };

  const columns = [
    {
      title: 'ID', dataIndex: 'id', key: 'id', width: 60,
    },
    {
      title: '故障类型', dataIndex: 'fault_type', key: 'fault_type',
      render: (v: string, r: AnalysisRecord) => (
        <Space>
          <Tag color={statusColors[r.status]}>{r.status === 'completed' ? '完成' : r.status === 'running' ? '诊断中' : r.status === 'failed' ? '失败' : '等待'}</Tag>
          <Text>{v || '-'}</Text>
        </Space>
      ),
    },
    {
      title: '严重度', dataIndex: 'severity', key: 'severity', width: 70,
      render: (v: string) => v ? <Tag color={severityColors[v]}>{severityText[v]}</Tag> : '-',
    },
    {
      title: '置信度', dataIndex: 'confidence', key: 'confidence', width: 80,
      render: (v: number) => v != null ? `${(v * 100).toFixed(0)}%` : '-',
    },
    {
      title: '触发', dataIndex: 'trigger_type', key: 'trigger_type', width: 60,
      render: (v: string) => v === 'auto' ? <Tag color="blue">自动</Tag> : <Tag>手动</Tag>,
    },
    {
      title: '耗时', dataIndex: 'duration_ms', key: 'duration_ms', width: 80,
      render: (v: number) => v != null ? `${v}ms` : '-',
    },
    {
      title: '时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (v: string) => v ? new Date(v).toLocaleString() : '-',
    },
    {
      title: '操作', key: 'action', width: 80,
      render: (_: any, r: AnalysisRecord) => (
        <Button size="small" onClick={() => viewDetail(r)}>查看</Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ReloadOutlined />} onClick={loadRecords}>刷新</Button>
        <Text type="secondary">共 {records.length} 条诊断记录</Text>
      </Space>

      <AutoHeightTable
        scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
        dataSource={records}
        columns={columns}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{ pageSize: 10, showSizeChanger: false }}
      />

      {/* 诊断结果详情弹窗 */}
      <Modal
        title={<><RobotOutlined /> AI诊断详情 #{selected?.id}</>}
        open={!!selected && resultModal !== null}
        onCancel={() => { setSelected(null); setResultModal(null); }}
        width={900}
        footer={<Button onClick={() => { setSelected(null); setResultModal(null); }}>关闭</Button>}
      >
        {resultModal && <DiagnosisResultCard result={resultModal} record={selected} />}
      </Modal>
    </div>
  );
}

export default DiagnosisHistory;
