/**
 * 天链V3 — 数据大屏核心指标卡片
 *
 * Phase48: 单个指标展示单元（标题/数值/单位/图标/子标签）
 */
import React from 'react';
import { CARD_BG, CARD_BORDER, PRIMARY_COLOR, TEXT_SECONDARY } from '../constants';

const MetricCard: React.FC<{
  title: string;
  value: number | string;
  unit?: string;
  color?: string;
  icon?: string;
  subLabel?: string;
  subValue?: string | number;
}> = ({ title, value, unit = '', color = PRIMARY_COLOR, icon = '', subLabel, subValue }) => (
  <div
    style={{
      background: CARD_BG,
      border: CARD_BORDER,
      borderRadius: 8,
      padding: '20px 24px',
      textAlign: 'center',
      backdropFilter: 'blur(4px)',
      WebkitBackdropFilter: 'blur(4px)',
    }}
  >
    {icon && <div style={{ fontSize: 28, marginBottom: 8 }}>{icon}</div>}
    <div style={{ fontSize: 13, color: TEXT_SECONDARY, marginBottom: 4 }}>{title}</div>
    <div style={{ fontSize: 36, fontWeight: 700, color }}>
      {value}
      {unit && <span style={{ fontSize: 16, marginLeft: 2, opacity: 0.8 }}>{unit}</span>}
    </div>
    {subLabel && subValue !== undefined && (
      <div style={{ fontSize: 12, color: TEXT_SECONDARY, marginTop: 4 }}>
        {subLabel}: {subValue}
      </div>
    )}
  </div>
);

export default MetricCard;
