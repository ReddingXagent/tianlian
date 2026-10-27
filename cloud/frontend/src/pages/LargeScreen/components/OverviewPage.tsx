/**
 * 天链V3 — 数据大屏 轮播页0：运行总览
 *
 * Phase48: 左侧核心指标卡片 + 右侧实时告警滚动与统计条
 */
import React from 'react';
import {
  CARD_BG,
  CARD_BORDER,
  DANGER_COLOR,
  PRIMARY_COLOR,
  SUCCESS_COLOR,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  WARNING_COLOR,
} from '../constants';
import type { LargeScreenData } from '../types';
import MetricCard from './MetricCard';
import AlarmTicker from './AlarmTicker';

const OverviewPage: React.FC<{ data: LargeScreenData }> = ({ data }) => {
  const { core_metrics } = data;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, height: '100%' }}>
      {/* 左侧：核心指标 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: TEXT_PRIMARY, textAlign: 'center' }}>
          天链运维平台 · 运行总览
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 16,
            flex: 1,
          }}
        >
          <MetricCard
            title="设备总数"
            value={core_metrics.total_devices}
            unit="台"
            icon="🖥️"
            color={PRIMARY_COLOR}
            subLabel="站点"
            subValue={core_metrics.total_stations}
          />
          <MetricCard
            title="在线设备"
            value={core_metrics.online_devices}
            unit={`/ ${core_metrics.total_devices}`}
            icon="🟢"
            color={SUCCESS_COLOR}
            subLabel="在线率"
            subValue={`${core_metrics.online_rate}%`}
          />
          <MetricCard
            title="活跃告警"
            value={core_metrics.active_alarms}
            unit="条"
            icon="🔴"
            color={DANGER_COLOR}
            subLabel="严重"
            subValue={core_metrics.critical_alarms}
          />
          <MetricCard
            title="待处理工单"
            value={core_metrics.pending_workorders}
            unit="个"
            icon="📋"
            color={WARNING_COLOR}
            subLabel="进行中"
            subValue={core_metrics.in_progress_workorders}
          />
        </div>
      </div>
      {/* 右侧：告警滚动 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: TEXT_PRIMARY }}>实时告警</div>
        <AlarmTicker alarms={data.recent_alarms} />
        <div
          style={{
            background: CARD_BG,
            border: CARD_BORDER,
            borderRadius: 8,
            padding: 12,
            display: 'flex',
            justifyContent: 'space-around',
            fontSize: 13,
          }}
        >
          <span style={{ color: TEXT_SECONDARY }}>严重: <b style={{ color: DANGER_COLOR }}>{core_metrics.critical_alarms}</b></span>
          <span style={{ color: TEXT_SECONDARY }}>今日新增: <b style={{ color: WARNING_COLOR }}>{data.alarm_stats.today_new}</b></span>
          <span style={{ color: TEXT_SECONDARY }}>待处理工单: <b style={{ color: WARNING_COLOR }}>{core_metrics.pending_workorders}</b></span>
        </div>
      </div>
    </div>
  );
};

export default OverviewPage;
