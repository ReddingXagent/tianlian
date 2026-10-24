/**
 * 功率趋势图（最近24小时：总功率 / 电池功率）
 */
import React from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import type { TelemetryData } from '../types';

const PowerTrendChart: React.FC<{ historyData: TelemetryData[] }> = ({ historyData }) => {
  const option = {
    title: {
      text: '功率趋势（最近24小时）',
    },
    tooltip: {
      trigger: 'axis',
    },
    legend: {
      data: ['总功率', '电池功率'],
    },
    xAxis: {
      type: 'category',
      data: historyData.map(d =>
        new Date(d.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
      ),
    },
    yAxis: {
      type: 'value',
      name: 'kW',
    },
    series: [
      {
        name: '总功率',
        type: 'line',
        data: historyData.map(d => d.grid_power_total || 0),
        smooth: true,
        lineStyle: { color: '#3f8600' },
      },
      {
        name: '电池功率',
        type: 'line',
        data: historyData.map(d => d.battery_power || 0),
        smooth: true,
        lineStyle: { color: '#f5a623' },
      },
    ],
  };

  return <ReactEChartsCore echarts={echarts} option={option} style={{ height: 300 }} />;
};

export default PowerTrendChart;
