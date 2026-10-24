/**
 * StatusDot - 统一状态指示器组件
 * 
 * Phase5 UI/UX优化: 提供一致的状态可视化元素
 * 使用 CSS 变量确保暗色/亮色模式适配
 * 
 * 用法:
 * <StatusDot status="online" text="在线" />
 * <StatusDot status="offline" pulse />
 * <StatusDot status="warning" size={12} />
 */
import React from 'react';
import type { CSSProperties } from 'react';

type StatusType = 'online' | 'offline' | 'warning' | 'error' | 'success' | 'idle' | 'maintenance';

interface StatusDotProps {
  /** 状态类型 */
  status: StatusType;
  /** 是否脉冲动画 */
  pulse?: boolean;
  /** 点大小 (px) */
  size?: number;
  /** 显示文本 */
  text?: string;
  /** 文本位置 */
  textPosition?: 'left' | 'right';
  /** 自定义颜色 (覆盖 status 的默认颜色) */
  color?: string;
  /** 自定义样式 */
  style?: CSSProperties;
}

const STATUS_COLORS: Record<StatusType, string> = {
  online: '#34a853',
  offline: '#ea4335',
  warning: '#f5a623',
  error: '#ea4335',
  success: '#34a853',
  idle: '#a0a0b8',
  maintenance: '#f5a623',
};

const STATUS_LABELS: Record<StatusType, string> = {
  online: '在线',
  offline: '离线',
  warning: '警告',
  error: '异常',
  success: '成功',
  idle: '空闲',
  maintenance: '维护中',
};

const StatusDot: React.FC<StatusDotProps> = ({
  status,
  pulse = false,
  size = 8,
  text,
  textPosition = 'right',
  color,
  style,
}) => {
  const baseColor = color || STATUS_COLORS[status];
  const label = text || STATUS_LABELS[status];
  const showPulse = pulse && (status === 'online' || status === 'warning' || status === 'error');

  const dotStyle: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    ...style,
  };

  return (
    <span style={dotStyle} className="status-dot">
      {textPosition === 'left' && text && (
        <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{label}</span>
      )}
      <span style={{ position: 'relative', display: 'inline-flex', width: size, height: size, flexShrink: 0 }}>
        {/* 脉冲外圈 */}
        {showPulse && (
          <span
            style={{
              position: 'absolute',
              inset: -4,
              borderRadius: '50%',
              background: baseColor,
              opacity: 0.3,
              animation: 'statusPulse 1.5s ease-in-out infinite',
            }}
          />
        )}
        {/* 核心点 */}
        <span
          style={{
            width: size,
            height: size,
            borderRadius: '50%',
            background: baseColor,
            display: 'inline-block',
            boxShadow: `0 0 ${size / 2}px ${baseColor}40`,
            flexShrink: 0,
          }}
        />
      </span>
      {textPosition === 'right' && text && (
        <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{label}</span>
      )}
    </span>
  );
};

export default StatusDot;

// 导出状态类型
export type { StatusType };
export { STATUS_COLORS, STATUS_LABELS };