/**
 * SOC 趋势图（最近24小时）
 */
import React from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import type { TelemetryData } from '../types';

const SOCTrendChart: React.FC<{ historyData: TelemetryData[] }> = ({ historyData }) => {
  const option = {
    title: {
      text: 'SOC趋势（最近24小时）',
    },
    tooltip: {
      trigger: 'axis',
    },
    xAxis: {
      type: 'category',
      data: historyData.map(d =>
        new Date(d.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
      ),
    },
    yAxis: {
      type: 'value',
      name: '%',
      min: 0,
      max: 100,
    },
    series: [
      {
        name: 'SOC',
        type: 'line',
        data: historyData.map(d => d.battery_soc || d.charger_soc || 0),
        smooth: true,
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: '#f5a623' },
              { offset: 1, color: '#f5a62300' },
            ],
          },
        },
      },
    ],
  };

  return <ReactEChartsCore echarts={echarts} option={option} style={{ height: 300 }} />;
};

export default SOCTrendChart;
