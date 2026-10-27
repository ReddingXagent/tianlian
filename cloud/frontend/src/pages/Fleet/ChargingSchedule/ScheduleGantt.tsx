/**
 * 充电调度甘特图
 *
 * 横轴 24h、纵轴车辆(车牌ID)；色块=充电时段，颜色深浅=分配功率
 * 背景: 尖峰平谷时段色带(谷=绿/平=蓝/峰=橙/尖=红)
 *
 * 数据来源: GET /fleet/charging/schedule/current 或 /{plan_id} 的 entries
 *           (含 start_time/end_time; generate 返回的条目无时间字段,不适用)
 */
import React, { useMemo } from 'react';
import { Empty } from 'antd';
import dayjs from 'dayjs';
import type { ScheduleEntry } from './types';

interface Props {
  entries: ScheduleEntry[];
  availablePowerKw?: number;
}

/** 工商业典型分时电价时段(可由电价库覆盖)。label 对应 谷/平/峰/尖 */
const PERIOD_BANDS = [
  { label: '谷', start: 0, end: 8, color: '#52c41a' },
  { label: '平', start: 8, end: 10, color: '#1890ff' },
  { label: '峰', start: 10, end: 12, color: '#fa8c16' },
  { label: '平', start: 12, end: 14, color: '#1890ff' },
  { label: '尖', start: 14, end: 17, color: '#f5222d' },
  { label: '平', start: 17, end: 19, color: '#1890ff' },
  { label: '峰', start: 19, end: 24, color: '#fa8c16' },
];

const LEGEND = [
  { label: '谷', color: '#52c41a' },
  { label: '平', color: '#1890ff' },
  { label: '峰', color: '#fa8c16' },
  { label: '尖', color: '#f5222d' },
];

const HOUR_TICKS = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22];

/** ISO 时间 → 小时(含分钟) */
function toHours(iso?: string | null): number | null {
  if (!iso) return null;
  const d = dayjs(iso);
  if (!d.isValid()) return null;
  return d.hour() + d.minute() / 60;
}

const ScheduleGantt: React.FC<Props> = ({ entries, availablePowerKw }) => {
  // 纵轴: 按 vehicle_id 去重, 组内按优先级排序
  const vehicles = useMemo(() => {
    const map = new Map<number, ScheduleEntry[]>();
    (entries || []).forEach(e => {
      if (!map.has(e.vehicle_id)) map.set(e.vehicle_id, []);
      map.get(e.vehicle_id)!.push(e);
    });
    return [...map.entries()]
      .map(([vid, list]) => ({ vid, list: list.sort((a, b) => a.priority - b.priority) }))
      .sort((a, b) => (a.list[0]?.priority ?? 99) - (b.list[0]?.priority ?? 99));
  }, [entries]);

  // 功率归一化基准(决定色块深浅)
  const maxPower = useMemo(() => {
    const m = Math.max(0, ...(entries || []).map(e => e.assigned_power_kw || 0));
    return Math.max(m, availablePowerKw || 0, 1);
  }, [entries, availablePowerKw]);

  if (!entries || entries.length === 0) {
    return <Empty data-testid="schedule-gantt" description="暂无调度数据" />;
  }

  const blockStyle = (e: ScheduleEntry): React.CSSProperties => {
    const s = toHours(e.start_time);
    const en = toHours(e.end_time);
    let left = s ?? 0;
    let right = en ?? left;
    if (right < left) right += 24; // 跨天
    left = Math.max(0, Math.min(left, 24));
    right = Math.max(left, Math.min(right, 24));
    const width = Math.max(0.5, ((right - left) / 24) * 100);
    const ratio = Math.max(0, Math.min((e.assigned_power_kw || 0) / maxPower, 1));
    let bg = 'rgba(0,0,0,0.10)'; // idle
    if (e.charge_mode === 'charge') bg = `rgba(24,144,255,${(0.3 + 0.7 * ratio).toFixed(2)})`;
    else if (e.charge_mode === 'discharge') bg = `rgba(245,34,45,${(0.5 + 0.45 * ratio).toFixed(2)})`;
    return {
      position: 'absolute', top: 4, bottom: 4,
      left: `${(left / 24) * 100}%`, width: `${width}%`,
      background: bg, borderRadius: 3,
    };
  };

  return (
    <div data-testid="schedule-gantt" style={{ width: '100%' }}>
      {/* 图例 */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 8, alignItems: 'center', fontSize: 12 }}>
        {LEGEND.map(l => (
          <span key={l.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <span style={{ display: 'inline-block', width: 14, height: 10, background: l.color, borderRadius: 2 }} />
            {l.label}
          </span>
        ))}
        <span style={{ color: '#999' }}>色块深浅 = 分配功率</span>
      </div>

      {/* 时间刻度 */}
      <div style={{ position: 'relative', height: 20, marginLeft: 96, borderBottom: '1px solid #f0f0f0' }}>
        {HOUR_TICKS.map(h => (
          <span key={h} style={{ position: 'absolute', left: `${(h / 24) * 100}%`, transform: 'translateX(-50%)', fontSize: 11, color: '#999' }}>
            {String(h).padStart(2, '0')}
          </span>
        ))}
        <span style={{ position: 'absolute', right: 0, fontSize: 11, color: '#999' }}>24</span>
      </div>

      {/* 车辆行 */}
      {vehicles.map(({ vid, list }) => (
        <div key={vid} style={{ display: 'flex', alignItems: 'center', height: 32, borderBottom: '1px dashed #f5f5f5' }}>
          <div style={{ width: 96, flexShrink: 0, fontSize: 12, color: '#333', paddingRight: 8, textAlign: 'right' }}>
            车辆 {vid}
          </div>
          <div style={{ position: 'relative', flex: 1, height: 28 }}>
            {/* 背景色带 */}
            {PERIOD_BANDS.map((b, i) => (
              <div key={i} style={{
                position: 'absolute', top: 0, bottom: 0,
                left: `${(b.start / 24) * 100}%`, width: `${((b.end - b.start) / 24) * 100}%`,
                background: b.color, opacity: 0.08,
              }} />
            ))}
            {/* 时段色块 */}
            {list.map(e => (
              <div key={e.id} data-testid="gantt-block" data-vehicle={vid}
                   data-mode={e.charge_mode} data-power={e.assigned_power_kw}
                   style={blockStyle(e)}
                   title={`车辆${vid} ${e.start_time ? dayjs(e.start_time).format('HH:mm') : ''}-${e.end_time ? dayjs(e.end_time).format('HH:mm') : ''} ${e.assigned_power_kw}kW (${e.charge_mode})`} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

export default ScheduleGantt;
