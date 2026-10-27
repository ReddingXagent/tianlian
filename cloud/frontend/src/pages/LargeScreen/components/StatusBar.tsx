/**
 * 天链V3 — 数据大屏底部状态指示条
 *
 * Phase48: 固定底部，展示刷新状态、数据更新时间、页面进度
 */
import React from 'react';
import { DANGER_COLOR, SUCCESS_COLOR, TEXT_SECONDARY } from '../constants';
import type { LargeScreenData } from '../types';

const StatusBar: React.FC<{
  data: LargeScreenData | null;
  loading: boolean;
  error: string | null;
  pageIndex: number;
}> = ({ data, loading, error, pageIndex }) => (
  <div
    style={{
      position: 'fixed',
      bottom: 0,
      left: 0,
      right: 0,
      height: 36,
      background: 'rgba(0,0,0,0.6)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 24,
      fontSize: 12,
      color: TEXT_SECONDARY,
      backdropFilter: 'blur(4px)',
      WebkitBackdropFilter: 'blur(4px)',
      zIndex: 100,
    }}
  >
    <span>
      天链运维平台 V3 · 大屏展示模式
    </span>
    <span>|</span>
    <span>
      {data
        ? `数据更新: ${new Date(data.timestamp).toLocaleTimeString('zh-CN')}`
        : '加载中...'}
    </span>
    <span>|</span>
    <span>
      {loading ? '刷新中...' : '每30秒自动刷新 ✓'}
    </span>
    <span>|</span>
    <span>
      页面 {pageIndex + 1}/3 ·
      <span
        style={{
          display: 'inline-block',
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: error ? DANGER_COLOR : SUCCESS_COLOR,
          marginLeft: 4,
          verticalAlign: 'middle',
        }}
      />
    </span>
  </div>
);

export default StatusBar;
