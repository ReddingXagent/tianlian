/**
 * 天链V3 — 数据大屏 轮播页1：站点健康与工单统计
 *
 * Phase48: 左侧站点健康分布饼图 + 右侧工单状态柱状图
 */
import React from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
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

const getHealthPieOption = (data: LargeScreenData) => {
  const { excellent, good, warning, critical } = data.health_distribution;
  return {
    tooltip: { trigger: 'item' as const, formatter: '{b}: {c} 站点 ({d}%)' },
    legend: {
      bottom: 0,
      textStyle: { color: TEXT_SECONDARY, fontSize: 11 },
      itemWidth: 12,
      itemHeight: 12,
    },
    series: [
      {
        type: 'pie',
        radius: ['30%', '55%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: false,
        label: { show: true, formatter: '{d}%', fontSize: 11, color: TEXT_PRIMARY },
        emphasis: { label: { show: true, fontSize: 14 } },
        data: [
          { value: excellent, name: '优秀', itemStyle: { color: SUCCESS_COLOR } },
          { value: good, name: '良好', itemStyle: { color: PRIMARY_COLOR } },
          { value: warning, name: '警告', itemStyle: { color: WARNING_COLOR } },
          { value: critical, name: '严重', itemStyle: { color: DANGER_COLOR } },
        ],
      },
    ],
  };
};

const getWorkOrderBarOption = (data: LargeScreenData) => {
  const { pending, in_progress, completed } = data.workorder_stats;
  return {
    tooltip: { trigger: 'axis' as const },
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category' as const,
      data: ['待处理', '进行中', '已完成'],
      axisLabel: { color: TEXT_SECONDARY, fontSize: 11 },
    },
    yAxis: {
      type: 'value' as const,
      minInterval: 1,
      axisLabel: { color: TEXT_SECONDARY, fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
    },
    series: [
      {
        type: 'bar',
        data: [
          { value: pending, itemStyle: { color: WARNING_COLOR } },
          { value: in_progress, itemStyle: { color: PRIMARY_COLOR } },
          { value: completed, itemStyle: { color: SUCCESS_COLOR } },
        ],
        barWidth: '40%',
        label: {
          show: true,
          position: 'top',
          color: TEXT_PRIMARY,
          fontSize: 12,
          formatter: (p: any) => p.value,
        },
      },
    ],
  };
};

const HealthPage: React.FC<{ data: LargeScreenData }> = ({ data }) => (
  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, height: '100%' }}>
    <div
      style={{
        background: CARD_BG,
        border: CARD_BORDER,
        borderRadius: 8,
        padding: 16,
      }}
    >
      <div style={{ fontSize: 16, fontWeight: 600, color: TEXT_PRIMARY, marginBottom: 12, textAlign: 'center' }}>
        站点健康分布
      </div>
      <ReactEChartsCore
        echarts={echarts}
        option={getHealthPieOption(data)}
        style={{ height: 320, width: '100%' }}
        opts={{ renderer: 'svg' }}
        notMerge
      />
    </div>
    <div
      style={{
        background: CARD_BG,
        border: CARD_BORDER,
        borderRadius: 8,
        padding: 16,
      }}
    >
      <div style={{ fontSize: 16, fontWeight: 600, color: TEXT_PRIMARY, marginBottom: 12, textAlign: 'center' }}>
        工单状态统计
      </div>
      <ReactEChartsCore
        echarts={echarts}
        option={getWorkOrderBarOption(data)}
        style={{ height: 320, width: '100%' }}
        opts={{ renderer: 'svg' }}
        notMerge
      />
    </div>
  </div>
);

export default HealthPage;
