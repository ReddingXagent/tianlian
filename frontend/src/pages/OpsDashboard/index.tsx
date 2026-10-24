/**
 * 运维大屏可视化 - 实时拓扑 + 事件流 + 健康度评分
 * Phase11 #59
 *
 * 三大核心模块：
 * 1. 实时拓扑：站点→网关→设备层级网络拓扑
 * 2. 事件流：告警/工单/自愈事件实时滚动
 * 3. 健康度评分：整体+各站点健康度仪表盘
 */
import React from 'react';
import { Spin } from 'antd';
import { COLORS } from './constants';
import { useOpsDashboard } from './hooks/useOpsDashboard';
import DashboardHeader from './components/DashboardHeader';
import TopologyPanel from './components/TopologyPanel';
import EventPanel from './components/EventPanel';
import HealthPanel from './components/HealthPanel';

const OpsDashboard: React.FC = () => {
  const {
    containerRef,
    selectedNode,
    setSelectedNode,
    eventListRef,
    loading,
    topology,
    events,
    health,
    overview,
    lastUpdate,
    refreshInterval,
    setRefreshInterval,
    isFullscreen,
    toggleFullscreen,
  } = useOpsDashboard();

  // 嵌套在 AppLayout 的 Content 内（含 margin/padding），不能再用 100vw/100vh ——
  // 那会叠加侧边栏与页面 padding 导致横向溢出、遮挡其他面板（卡 fcfd13fd）。
  // 高度 = 视口 - Header(64) - Content margin(32) - Content padding(48)
  const pageHeight = 'calc(100vh - 64px - 32px - 48px)';

  if (loading) {
    return (
      <div style={{ width: '100%', height: pageHeight, display: 'flex', alignItems: 'center', justifyContent: 'center', background: COLORS.bg }}>
        <Spin size="large" tip="加载大屏数据..." />
      </div>
    );
  }

  return (
    <div ref={containerRef} style={{ width: '100%', height: pageHeight, background: COLORS.bg, color: COLORS.text, overflow: 'hidden', position: 'relative' }}>

      {/* ─── 顶部标题栏 ─── */}
      <DashboardHeader
        lastUpdate={lastUpdate}
        refreshInterval={refreshInterval}
        onIntervalChange={setRefreshInterval}
        isFullscreen={isFullscreen}
        onToggleFullscreen={toggleFullscreen}
      />

      {/* ─── 主体三栏布局 ─── */}
      <div style={{ display: 'flex', height: 'calc(100% - 56px)', padding: 12, gap: 12, boxSizing: 'border-box', minWidth: 0 }}>
        {/* ─── 左栏: 实时拓扑 ─── */}
        <TopologyPanel topology={topology} selectedNode={selectedNode} onNodeClick={setSelectedNode} events={events} />

        {/* ─── 中栏: 事件流 ─── */}
        <EventPanel overview={overview} events={events} listRef={eventListRef} />

        {/* ─── 右栏: 健康度评分 ─── */}
        <HealthPanel health={health} overview={overview} />
      </div>
    </div>
  );
};

export default OpsDashboard;
