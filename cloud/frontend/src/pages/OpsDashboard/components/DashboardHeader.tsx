/**
 * 运维大屏顶部标题栏
 */
import React from 'react';
import { Tag, Tooltip } from 'antd';
import {
  DashboardOutlined, SyncOutlined,
  FullscreenOutlined, FullscreenExitOutlined,
} from '@ant-design/icons';
import { COLORS } from '../constants';

const DashboardHeader: React.FC<{
  lastUpdate: string;
  refreshInterval: number;
  onIntervalChange: (v: number) => void;
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
}> = ({ lastUpdate, refreshInterval, onIntervalChange, isFullscreen, onToggleFullscreen }) => (
  <div style={{
    height: 56,
    background: 'linear-gradient(180deg, rgba(6, 30, 65, 0.95) 0%, rgba(6, 30, 65, 0.7) 100%)',
    borderBottom: `1px solid ${COLORS.border}`,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 24px',
  }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <DashboardOutlined style={{ fontSize: 24, color: COLORS.accent }} />
      <span style={{ fontSize: 20, fontWeight: 700, letterSpacing: 4 }}>天链运维大屏</span>
      <Tag color="blue" style={{ marginLeft: 8 }}>实时</Tag>
    </div>
    <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
      <span style={{ color: COLORS.textDim, fontSize: 13 }}>
        <SyncOutlined spin style={{ marginRight: 4 }} />
        <span style={{ marginRight: 10 }}>
          <Tooltip title="点击切换刷新频率">
            <span
              onClick={() => {
                const steps = [30, 60, 90, 120];
                const i = steps.indexOf(refreshInterval);
                onIntervalChange(steps[(i + 1) % steps.length] ?? 30);
              }}
              style={{ cursor: 'pointer', userSelect: 'none', color: COLORS.textDim }}>
              刷新间隔 {refreshInterval}s
            </span>
          </Tooltip>
        </span>
        最后更新: {lastUpdate}
      </span>
      <Tooltip title={isFullscreen ? '退出全屏' : '全屏'}>
        <div onClick={onToggleFullscreen} style={{ cursor: 'pointer', color: COLORS.accent, fontSize: 18 }}>
          {isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
        </div>
      </Tooltip>
    </div>
  </div>
);

export default DashboardHeader;
