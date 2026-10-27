import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { LineChart as ELine } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import React from 'react';

echarts.use([ELine, GridComponent, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer]);

interface LineChartProps {
  option?: Record<string, any>;
  style?: React.CSSProperties;
  [key: string]: any;
}

const defaultOption = {
  xAxis: { type: 'category', data: [] },
  yAxis: { type: 'value' },
  series: [{ type: 'line', data: [] }],
};

const LineChart: React.FC<LineChartProps> = ({ option = defaultOption, style, ...rest }) => (
  <ReactEChartsCore echarts={echarts} option={option} style={style} {...rest} />
);

export default LineChart;
