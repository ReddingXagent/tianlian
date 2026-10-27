/**
 * 天链V3 — 数据大屏独立展示模式 Vitest 测试
 *
 * Phase48: 覆盖 LargeScreen 组件的渲染、数据加载、页面切换
 */
import { render, screen, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import api from '../../../api';

// ─── Mock echarts ─────────────────────────────────

vi.mock('echarts-for-react/lib/core', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock('echarts/core', () => ({
  __esModule: true,
  default: {},
  init: vi.fn(() => ({
    setOption: vi.fn(),
    dispose: vi.fn(),
    resize: vi.fn(),
  })),
  registerTheme: vi.fn(),
  registerMap: vi.fn(),
  connect: vi.fn(),
  disconnect: vi.fn(),
  graphic: {},
  use: vi.fn(),
}));

// Mock specific echarts chart/renderer modules
vi.mock('echarts/charts', () => ({ PieChart: {}, BarChart: {}, LineChart: {} }));
vi.mock('echarts/components', () => ({
  GridComponent: {},
  TooltipComponent: {},
  LegendComponent: {},
  TitleComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));

// ─── Mock API ─────────────────────────────────────

const mockLargeScreenData = {
  core_metrics: {
    total_devices: 58,
    online_devices: 54,
    fault_devices: 2,
    offline_devices: 2,
    online_rate: 93.1,
    total_stations: 16,
    active_alarms: 3,
    critical_alarms: 1,
    pending_workorders: 5,
    in_progress_workorders: 3,
  },
  health_distribution: { excellent: 8, good: 5, warning: 2, critical: 1 },
  station_health: [
    { station_id: 1, station_name: '北京朝阳站', health_score: 92, device_count: 8, online_count: 7, fault_count: 0 },
    { station_id: 2, station_name: '上海浦东站', health_score: 85, device_count: 6, online_count: 5, fault_count: 1 },
  ],
  recent_alarms: [
    { id: 1, title: '温度过高', level: 'critical', device_name: '设备1', station_name: '北京站', created_at: new Date().toISOString() },
    { id: 2, title: '通讯中断', level: 'warning', device_name: '设备2', station_name: '上海站', created_at: new Date().toISOString() },
  ],
  workorder_stats: { pending: 5, in_progress: 3, completed: 20, today_new_alarms: 2 },
  alarm_stats: { active: 3, critical: 1, warning: 2, today_new: 2 },
  device_type_stats: [
    { type: '光伏逆变器', total: 20, online: 19, rate: 95 },
    { type: '储能PCS', total: 15, online: 14, rate: 93.3 },
  ],
  timestamp: new Date().toISOString(),
};

vi.mock('../../../api', () => ({
  default: {
    get: vi.fn(),
  },
}));

// ─── 辅助: 渲染组件 ──────────────────────────────

import LargeScreen from '../index';

// userEvent 懒加载辅助（vitest 环境下初始化一次）
let _userEvent: any = null;
async function importSetup() {
  if (!_userEvent) {
    const mod = await import('@testing-library/user-event');
    _userEvent = mod.default.setup();
  }
  return { userEvent: _userEvent };
}

const renderLargeScreen = async () => {
  let container: HTMLElement | undefined;
  await act(async () => {
    const result = render(<LargeScreen />);
    container = result.container;
  });
  return container!;
};

// ─── 测试 ─────────────────────────────────────────

describe('LargeScreen 组件', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // 模拟 localStorage
    window.localStorage.setItem('admin_token', 'test-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('应渲染加载状态', () => {
    // 给一个永不resolve的promise来测试loading状态
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}));
    const { container } = render(<LargeScreen />);
    expect(container).toBeTruthy();
    // 应显示加载文本
    expect(container.textContent).toContain('加载大屏数据');
  });

  it('应成功加载并渲染数据', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: mockLargeScreenData });

    const container = await renderLargeScreen();

    // 验证标题
    expect(container.textContent).toContain('天链运维');
    expect(container.textContent).toContain('监控大屏');

    // 在页面0，验证核心指标
    expect(container.textContent).toContain('设备总数');

    // API被调用过（路径应为 dashboard/large-screen）
    expect(vi.mocked(api.get)).toHaveBeenCalledWith('/dashboard/large-screen');
  });

  it('应在API失败时显示错误态而非mock假数据', async () => {
    // 首次调用失败
    vi.mocked(api.get).mockRejectedValue(new Error('Network error'));

    const container = await renderLargeScreen();

    // 标题仍渲染，但主体是错误提示
    expect(container.textContent).toContain('天链运维');
    expect(container.textContent).toContain('数据加载失败');
    // 应提供重试入口
    expect(container.textContent).toContain('重试');

    // 绝不能回退渲染假站点/假指标（mockData.ts 已删除）
    expect(container.textContent).not.toContain('设备总数');
    expect(container.textContent).not.toContain('北京朝阳站');
    expect(container.textContent).not.toContain('上海浦东站');

    expect(vi.mocked(api.get)).toHaveBeenCalledWith('/dashboard/large-screen');
  });

  it('错误态点击重试应重新拉取数据并可恢复', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(new Error('Network error'));
    const { userEvent } = await importSetup();
    const container = await renderLargeScreen();
    expect(container.textContent).toContain('数据加载失败');

    // 恢复API后点击重试
    vi.mocked(api.get).mockResolvedValue({ data: mockLargeScreenData });
    const retryBtn = screen.getByText('重试');
    await userEvent.click(retryBtn);

    await waitFor(() => {
      expect(container.textContent).toContain('设备总数');
    });
  });

  it('应渲染核心指标准确', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: mockLargeScreenData });

    const container = await renderLargeScreen();

    // 页面0显示核心指标
    expect(container.textContent).toContain('58');
    expect(container.textContent).toContain('54');
    expect(container.textContent).toContain('93.1');
  });

  it('应显示导航点', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: mockLargeScreenData });

    const container = await renderLargeScreen();

    // 页面应该有导航点指示器
    const dots = container.querySelectorAll('[style*="border-radius: 50%"]');
    expect(dots.length).toBeGreaterThanOrEqual(3);
  });

  it('应显示状态栏', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: mockLargeScreenData });

    const container = await renderLargeScreen();

    // 状态栏包含页面指示
    expect(container.textContent).toContain('页面');
    expect(container.textContent).toContain('/3');
  });
});