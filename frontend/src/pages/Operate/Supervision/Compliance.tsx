/**
 * 天链 V3 — 合规检查报告
 * 查看各城市监管平台的合规检查记录与得分
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Table, Tag, Button, Progress } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { complianceAPI } from '../../../api/operateExternal';
import { fetchAllPages } from '../../../api/fetchAll';

interface ComplianceItem {
  id: number;
  config_id: number;
  city: string;
  check_type: string;
  result: string;
  score: number;
  details?: Record<string, unknown> | null;
  checked_at?: string;
  created_at?: string;
}

const CHECK_TYPE_MAP: Record<string, string> = {
  data_integrity: '数据完整性',
  report_delay: '上报时延',
  compliance: '合规性',
};

const RESULT_MAP: Record<string, { color: string; text: string }> = {
  pass: { color: 'green', text: '通过' },
  warn: { color: 'orange', text: '警告' },
  fail: { color: 'red', text: '不通过' },
};

const scoreColor = (score: number) => {
  if (score >= 90) return '#52c41a';
  if (score >= 60) return '#faad14';
  return '#ff4d4f';
};

const SupervisionCompliance: React.FC = () => {
  const [data, setData] = useState<ComplianceItem[]>([]);
  const [loading, setLoading] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // 卡 fb183aaf: page_size 恰 100 上限会静默截断 → fetchAllPages 循环拉全量
      const items = await fetchAllPages<ComplianceItem>(complianceAPI.list);
      setData(items);
    } catch {
      setData([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '城市', dataIndex: 'city', key: 'city', width: 90 },
    {
      title: '检查类型', dataIndex: 'check_type', key: 'check_type', width: 120,
      render: (v: string) => <Tag color="blue">{CHECK_TYPE_MAP[v] || v}</Tag>,
    },
    {
      title: '结果', dataIndex: 'result', key: 'result', width: 90,
      render: (v: string) => <Tag color={RESULT_MAP[v]?.color || 'default'}>{RESULT_MAP[v]?.text || v}</Tag>,
    },
    {
      title: '合规得分', dataIndex: 'score', key: 'score', width: 180,
      render: (v: number) => (
        <Progress
          percent={v ?? 0}
          size="small"
          format={(p) => <span style={{ color: scoreColor(p ?? 0), fontWeight: 600 }}>{(p ?? 0).toFixed(1)}</span>}
          strokeColor={scoreColor(v ?? 0)}
        />
      ),
    },
    { title: '检查时间', dataIndex: 'checked_at', key: 'checked_at', width: 160, render: (v: string) => v || '-' },
  ];

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
        <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
      </div>
      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        scroll={{ x: 800 }}
        pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
      />
    </>
  );
};

export default SupervisionCompliance;
