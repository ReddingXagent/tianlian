/**
 * 天链V3 — 数据大屏 轮播页2：设备类型分布与站点详情
 *
 * Phase48: 左侧设备类型饼图 + 右侧站点健康详情列表
 */
import React from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import {
  CARD_BG,
  CARD_BORDER,
  DANGER_COLOR,
  SUCCESS_COLOR,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  WARNING_COLOR,
} from '../constants';
import type { LargeScreenData } from '../types';

const getDeviceTypePieOption = (data: LargeScreenData) => {
  if (data.device_type_stats.length === 0) return {};
  const colors = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452'];
  return {
    tooltip: { trigger: 'item' as const, formatter: '{b}: {c} 台 ({d}%)' },
    legend: {
      bottom: 0,
      textStyle: { color: TEXT_SECONDARY, fontSize: 11 },
      itemWidth: 12,
      itemHeight: 12,
    },
    series: [
      {
        type: 'pie',
        radius: '50%',
        center: ['50%', '45%'],
        label: { show: true, formatter: '{b}', fontSize: 10, color: TEXT_PRIMARY },
        data: data.device_type_stats.map((d, i) => ({
          value: d.total,
          name: d.type,
          itemStyle: { color: colors[i % colors.length] },
        })),
      },
    ],
  };
};

const DeviceTypePage: React.FC<{ data: LargeScreenData }> = ({ data }) => (
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
        设备类型分布
      </div>
      <ReactEChartsCore
        echarts={echarts}
        option={getDeviceTypePieOption(data)}
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
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div style={{ fontSize: 16, fontWeight: 600, color: TEXT_PRIMARY, marginBottom: 12, textAlign: 'center' }}>
        站点健康详情
      </div>
      <div style={{ flex: 1, overflow: 'auto' }}>
        {data.station_health.length === 0 ? (
          <div style={{ color: TEXT_SECONDARY, textAlign: 'center', paddingTop: 60 }}>
            暂无站点数据
          </div>
        ) : (
          data.station_health.map((s) => (
            <div
              key={s.station_id}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '8px 12px',
                marginBottom: 6,
                background: 'rgba(24,144,255,0.08)',
                borderRadius: 6,
                fontSize: 13,
              }}
            >
              <span style={{ color: TEXT_PRIMARY }}>{s.station_name}</span>
              <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
                <span style={{ color: TEXT_SECONDARY }}>
                  设备 <b style={{ color: TEXT_PRIMARY }}>{s.device_count}</b>
                </span>
                <span style={{ color: TEXT_SECONDARY }}>
                  在线 <b style={{ color: SUCCESS_COLOR }}>{s.online_count}</b>
                </span>
                <span
                  style={{
                    color: s.health_score >= 80 ? SUCCESS_COLOR : s.health_score >= 60 ? WARNING_COLOR : DANGER_COLOR,
                    fontWeight: 600,
                  }}
                >
                  健康 {s.health_score}分
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  </div>
);

export default DeviceTypePage;
