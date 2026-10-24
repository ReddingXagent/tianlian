/**
 * 温度趋势图（最近24小时：机内温度 / 环境温度）
 */
import React from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import type { TelemetryData } from '../types';

const TemperatureTrendChart: React.FC<{ historyData: TelemetryData[] }> = ({ historyData }) => {
  const option = {
    title: {
      text: '温度趋势（最近24小时）',
    },
    tooltip: {
      trigger: 'axis',
    },
    legend: {
      data: ['机内温度', '环境温度'],
    },
    xAxis: {
      type: 'category',
      data: historyData.map(d =>
        new Date(d.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
      ),
    },
    yAxis: {
      type: 'value',
      name: '℃',
    },
    series: [
      {
        name: '机内温度',
        type: 'line',
        data: historyData.map(d => d.internal_temperature || 0),
        smooth: true,
        lineStyle: { color: '#cf1322' },
      },
      {
        name: '环境温度',
        type: 'line',
        data: historyData.map(d => d.ambient_temperature || 0),
        smooth: true,
        lineStyle: { color: '#34a853' },
      },
    ],
  };

  return <ReactEChartsCore echarts={echarts} option={option} style={{ height: 300 }} />;
};

export default TemperatureTrendChart;
