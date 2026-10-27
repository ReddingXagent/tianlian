/**
 * EfficiencyOverviewCard — 请求收敛测试 (卡片 fb99dc96)
 *
 * 断言：挂载只触发一轮聚合请求；切换 filterType 只新增一轮。
 * 背景：曾有两个 useEffect 双触发（挂载×2、筛选切换×2）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import React from 'react';

// ═══════════════════════════════════════════
// Mock API 模块
// ═══════════════════════════════════════════
const { mockEfficiencyAPI } = vi.hoisted(() => ({
  mockEfficiencyAPI: {
    utilization: vi.fn(),
    efficiency: vi.fn(),
    generation: vi.fn(),
  },
}));

vi.mock('../../../api', () => ({
  efficiencyAPI: mockEfficiencyAPI,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}));

// ═══════════════════════════════════════════
// Mock ECharts（jsdom 下 Canvas 渲染报错）
// ═══════════════════════════════════════════
vi.mock('echarts-for-react/lib/core', () => ({
  default: () => React.createElement('div', { 'data-testid': 'echarts-mock' }),
}));

vi.mock('echarts/core', () => ({
  default: { use: vi.fn() },
  use: vi.fn(),
}));

vi.mock('echarts/charts', () => ({
  GaugeChart: {},
  BarChart: {},
}));

vi.mock('echarts/components', () => ({
  GridComponent: {},
  TooltipComponent: {},
  LegendComponent: {},
  TitleComponent: {},
}));

vi.mock('echarts/renderers', () => ({
  CanvasRenderer: {},
}));

import EfficiencyOverviewCard from '../EfficiencyOverviewCard';

const emptyReport = { data: [] as never[] };

beforeEach(() => {
  vi.clearAllMocks();
  mockEfficiencyAPI.utilization.mockResolvedValue({ data: emptyReport });
  mockEfficiencyAPI.efficiency.mockResolvedValue({ data: emptyReport });
  mockEfficiencyAPI.generation.mockResolvedValue({ data: emptyReport });
});

describe('EfficiencyOverviewCard — 请求收敛 (卡片 fb99dc96)', () => {
  it('挂载后聚合端点只请求 1 次（非 2 次）', async () => {
    render(<EfficiencyOverviewCard refreshInterval={0} />);

    await waitFor(() => {
      expect(mockEfficiencyAPI.utilization).toHaveBeenCalled();
    });
    // 等待微任务排空，确保重复调用（若有）都已发生
    await waitFor(() => {
      expect(mockEfficiencyAPI.efficiency).toHaveBeenCalledTimes(1);
    });

    expect(mockEfficiencyAPI.utilization).toHaveBeenCalledTimes(1);
    expect(mockEfficiencyAPI.efficiency).toHaveBeenCalledTimes(1);
    expect(mockEfficiencyAPI.generation).toHaveBeenCalledTimes(1);
  });

  it('切换 filterType 后只新增 1 次请求（非 2 次）', async () => {
    render(<EfficiencyOverviewCard refreshInterval={0} />);

    await waitFor(() => {
      expect(mockEfficiencyAPI.utilization).toHaveBeenCalledTimes(1);
    });

    // 打开下拉并选择「充电桩」
    fireEvent.mouseDown(screen.getByRole('combobox'));
    const option = await waitFor(() => {
      const el = screen.getByText('充电桩', { selector: '.ant-select-item-option-content' });
      expect(el).toBeTruthy();
      return el;
    });
    fireEvent.click(option);

    await waitFor(() => {
      expect(mockEfficiencyAPI.utilization).toHaveBeenCalledTimes(2);
    });
    expect(mockEfficiencyAPI.efficiency).toHaveBeenCalledTimes(2);
    expect(mockEfficiencyAPI.generation).toHaveBeenCalledTimes(2);

    // 稳定期：不再有第三次
    await new Promise((r) => setTimeout(r, 50));
    expect(mockEfficiencyAPI.utilization).toHaveBeenCalledTimes(2);
  });
});
