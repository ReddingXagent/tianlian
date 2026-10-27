import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart as EBar } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import React from 'react';

echarts.use([EBar, GridComponent, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer]);

interface BarChartProps {
  option?: Record<string, any>;
  style?: React.CSSProperties;
  [key: string]: any;
}

const defaultOption = {
  xAxis: { type: 'category', data: [] },
  yAxis: { type: 'value' },
  series: [{ type: 'bar', data: [] }],
};

const BarChart: React.FC<BarChartProps> = ({ option = defaultOption, style, ...rest }) => (
  <ReactEChartsCore echarts={echarts} option={option} style={style} {...rest} />
);

export default BarChart;
