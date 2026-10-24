import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { PieChart as EPie } from 'echarts/charts';
import { TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import React from 'react';

echarts.use([EPie, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer]);

interface PieChartProps {
  option?: Record<string, any>;
  style?: React.CSSProperties;
  [key: string]: any;
}

const defaultOption = {
  series: [{ type: 'pie', data: [] }],
};

const PieChart: React.FC<PieChartProps> = ({ option = defaultOption, style, ...rest }) => (
  <ReactEChartsCore echarts={echarts} option={option} style={style} {...rest} />
);

export default PieChart;
