/**
 * 天链V3 — 数据大屏独立展示模式
 *
 * Phase48: 面向监控大屏/电视墙的独立展示模式
 *
 * 功能：
 * - 大屏自适应布局（1920x1080 基准）
 * - 核心指标卡片（设备总量、在线、告警、工单）
 * - 站点健康分布（echarts 饼图）
 * - 告警实时滚动条
 * - 工单/设备在线统计
 * - 自动轮播/页面切换（每30秒）
 */
import React from 'react';
import * as echarts from 'echarts/core';
import { PieChart, BarChart, LineChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  PieChart,
  BarChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  CanvasRenderer,
]);

import { DARK_BG, DANGER_COLOR, PRIMARY_COLOR, TEXT_PRIMARY, TEXT_SECONDARY } from './constants';
import { useLargeScreenData } from './hooks/useLargeScreenData';
import OverviewPage from './components/OverviewPage';
import HealthPage from './components/HealthPage';
import DeviceTypePage from './components/DeviceTypePage';
import StatusBar from './components/StatusBar';
import PageDots from './components/PageDots';

// ─── 主组件 ──────────────────────────────────────

const LargeScreen: React.FC = () => {
  const { data, loading, error, pageIndex, setPageIndex, refresh } = useLargeScreenData();

  // ── 渲染当前页面 ──

  const renderPage = () => {
    if (!data) return null;

    switch (pageIndex) {
      // 页面0: 核心指标 + 告警滚动
      case 0:
        return <OverviewPage data={data} />;
      // 页面1: 站点健康分布 + 工单统计
      case 1:
        return <HealthPage data={data} />;
      // 页面2: 设备类型分布 + 站点列表
      case 2:
        return <DeviceTypePage data={data} />;
      default:
        return null;
    }
  };

  return (
    <div
      style={{
        width: '100vw',
        height: '100vh',
        background: DARK_BG,
        color: TEXT_PRIMARY,
        fontFamily: "'PingFang SC', 'Microsoft YaHei', sans-serif",
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {/* 背景装饰 */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background:
            'radial-gradient(ellipse at 20% 50%, rgba(24,144,255,0.06) 0%, transparent 50%), radial-gradient(ellipse at 80% 50%, rgba(82,196,26,0.04) 0%, transparent 50%)',
          pointerEvents: 'none',
          zIndex: 0,
        }}
      />

      {/* 顶部标题 */}
      <div
        style={{
          position: 'relative',
          zIndex: 1,
          padding: '16px 32px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderBottom: '1px solid rgba(24,144,255,0.15)',
        }}
      >
        <div style={{ fontSize: 13, color: TEXT_SECONDARY }}>
          {data
            ? new Date(data.timestamp).toLocaleString('zh-CN')
            : '加载中...'}
        </div>
        <div style={{ fontSize: 18, fontWeight: 700, letterSpacing: 4 }}>
          ⚡ 天链运维 · 监控大屏
        </div>
        <div style={{ fontSize: 13, color: TEXT_SECONDARY }}>
          {loading ? '🔄 数据刷新中...' : '✅ 数据正常'}
        </div>
      </div>

      {/* 主内容 */}
      <div
        style={{
          position: 'relative',
          zIndex: 1,
          padding: '24px 32px',
          height: 'calc(100vh - 36px - 53px)', // 减去状态栏和标题栏
          overflow: 'hidden',
        }}
      >
        {loading && !data ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              flexDirection: 'column',
              gap: 16,
            }}
          >
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: '50%',
                border: '3px solid rgba(24,144,255,0.3)',
                borderTopColor: PRIMARY_COLOR,
                animation: 'spin 0.8s linear infinite',
              }}
            />
            <div style={{ color: TEXT_SECONDARY, fontSize: 14 }}>正在加载大屏数据...</div>
          </div>
        ) : error ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: DANGER_COLOR,
              fontSize: 16,
              flexDirection: 'column',
              gap: 16,
            }}
          >
            <div>
              {error}
              {data ? '（展示最近一次成功数据）' : ''}
            </div>
            <button
              onClick={() => refresh()}
              style={{
                padding: '8px 24px',
                background: 'transparent',
                border: `1px solid ${PRIMARY_COLOR}`,
                borderRadius: 4,
                color: PRIMARY_COLOR,
                fontSize: 14,
                cursor: 'pointer',
              }}
            >
              重试
            </button>
          </div>
        ) : (
          renderPage()
        )}
      </div>

      {/* 导航点 */}
      <PageDots pageIndex={pageIndex} onSelect={setPageIndex} />

      {/* 状态栏 */}
      <StatusBar data={data} loading={loading} error={error} pageIndex={pageIndex} />

      {/* 全局动画 */}
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @keyframes tickerScroll {
          0% { transform: translateY(0); }
          100% { transform: translateY(-100%); }
        }
      `}</style>
    </div>
  );
};

export default LargeScreen;
