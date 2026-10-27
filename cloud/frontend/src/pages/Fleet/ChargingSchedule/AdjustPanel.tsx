/**
 * 动态调整面板
 *
 * 选中计划后编辑功率分配 → PATCH /fleet/charging/schedule/{id}/adjust
 * body: { new_distribution: [{ entry_id, new_power_kw }, ...] }
 */
import React, { useEffect, useState } from 'react';
import { Drawer, Table, InputNumber, Button, Tag, Spin, message } from 'antd';
import api from '../../../api';
import type { SchedulePlan, ScheduleEntry } from './types';

interface Props {
  open: boolean;
  plan: SchedulePlan | null;
  onClose: () => void;
  onSuccess: () => void;
}

const AdjustPanel: React.FC<Props> = ({ open, plan, onClose, onSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [entries, setEntries] = useState<ScheduleEntry[]>([]);
  // 编辑后功率: entryId -> kW
  const [powerMap, setPowerMap] = useState<Record<number, number>>({});

  useEffect(() => {
    if (!open || !plan) return;
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const { data } = await api.get(`/fleet/charging/schedule/${plan.id}`);
        if (cancelled) return;
        const list: ScheduleEntry[] = data?.entries || [];
        setEntries(list);
        const m: Record<number, number> = {};
        list.forEach(e => { m[e.id] = e.assigned_power_kw; });
        setPowerMap(m);
      } catch {
        if (!cancelled) setEntries([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [open, plan]);

  const handleSubmit = async () => {
    if (!plan) return;
    const new_distribution = entries.map(e => ({
      entry_id: e.id,
      new_power_kw: powerMap[e.id] ?? e.assigned_power_kw,
    }));
    try {
      await api.patch(`/fleet/charging/schedule/${plan.id}/adjust`, { new_distribution });
      message.success('调度调整成功');
      onSuccess();
    } catch (err: any) {
      message.error('调整失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const columns = [
    { title: '车辆ID', dataIndex: 'vehicle_id', key: 'vehicle_id', width: 80 },
    { title: '模式', dataIndex: 'charge_mode', key: 'charge_mode', width: 90,
      render: (v: string) => <Tag color={v === 'charge' ? 'blue' : v === 'discharge' ? 'red' : 'default'}>{v}</Tag> },
    { title: '优先级', dataIndex: 'priority', key: 'priority', width: 70, align: 'right' as const },
    { title: '分配功率(kW)', key: 'power',
      render: (_: unknown, r: ScheduleEntry) => (
        <InputNumber value={powerMap[r.id]} min={0} step={0.5} style={{ width: 120 }}
          onChange={v => setPowerMap(prev => ({ ...prev, [r.id]: v ?? 0 }))} />
      ) },
    { title: '时段', dataIndex: 'period_type', key: 'period_type', width: 80,
      render: (v: string | null) => v || '-' },
  ];

  return (
    <Drawer title={`动态调整 · 计划 #${plan?.id ?? ''}`} open={open} onClose={onClose} width={620}
      extra={<Button type="primary" onClick={handleSubmit}>提交调整</Button>}
    >
      <Spin spinning={loading}>
        <Table columns={columns} dataSource={entries} rowKey="id" size="small" pagination={false}
          locale={{ emptyText: '暂无调度条目' }}
        />
      </Spin>
    </Drawer>
  );
};

export default AdjustPanel;
