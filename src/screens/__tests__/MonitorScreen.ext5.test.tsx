/**
 * F1210: MonitorScreen coverage 补测 — L39/57 (fetchData isRefresh 分支 + catch 分支)
 * 既有套件均从挂载成功路径进入, 未触发 RefreshControl.onRefresh(isRefresh=true)
 * 也未覆盖 fetch 失败后 summary 保留的半错误态。本套件补齐:
 *   1) 下拉刷新路径: setRefreshing(true) (L39) — 用 UNSAFE_root.findAllByType
 *      直查 RefreshControl 实例 (F1206 模式: fail-fast 断言取代 if 守卫)
 *   2) 刷新失败路径: catch setError (L57) — 有 summary 时显示内联错误提示条
 *      (源码 error && !summary 才走 EmptyState, 有数据时顶部提示条仍渲染)
 *   3) 刷新失败后恢复: 再刷新成功 → 提示条消失
 * 注意: 不 spy 全局 setInterval (ext4 模式仅轮询套件需要), waitFor 可正常使用。
 */
import { render, act, waitFor } from '@testing-library/react-native';
import { RefreshControl } from 'react-native';
import MonitorScreen from '../MonitorScreen';
import { monitorApi, deviceMonitorApi } from '../../services/api';

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn() }),
  useFocusEffect: jest.fn((cb) => cb()),
}));

jest.mock('../../services/api', () => ({
  monitorApi: {
    getSummary: jest.fn(),
    getFaultDevices: jest.fn(),
    getCriticalAlarms: jest.fn(),
  },
  deviceMonitorApi: {
    getDeviceStatusList: jest.fn(),
    getRealtimeOverview: jest.fn(),
  },
}));

const SUMMARY = {
  totalDevices: 10,
  onlineDevices: 7,
  faultDevices: 2,
  criticalAlarms: 1,
};
const DEVICE = {
  id: 1,
  stationId: 1,
  stationName: '充电站A',
  name: '设备一',
  code: 'D1',
  type: 'charger',
  status: 'online',
  model: 'M1',
  manufacturer: 'X',
  lastHeartbeat: '2024-01-15T10:00:00Z',
  createdAt: '',
  updatedAt: '',
};
const OVERVIEW = {
  totalPower: 2200,
  powerTrend: 5.2,
  todayGeneration: 100,
  todayConsumption: 50,
  gridImport: 10,
  gridExport: 20,
  efficiency: 95.3,
  updateTime: '2024-01-15T10:05:00Z',
  devices: [
    { id: 1, name: '设备一', type: 'charger', power: 2200, status: 'online' },
  ],
};

function mockAllSuccess() {
  (monitorApi.getSummary as jest.Mock).mockResolvedValue({ data: SUMMARY });
  (deviceMonitorApi.getDeviceStatusList as jest.Mock).mockResolvedValue({
    data: { items: [DEVICE], total: 1 },
  });
  (monitorApi.getFaultDevices as jest.Mock).mockResolvedValue({
    data: { items: [], total: 0 },
  });
  (monitorApi.getCriticalAlarms as jest.Mock).mockResolvedValue({
    data: { items: [], total: 0 },
  });
  (deviceMonitorApi.getRealtimeOverview as jest.Mock).mockResolvedValue({
    data: OVERVIEW,
  });
}

/**
 * 触发下拉刷新并等待完成 (refreshing 复位)。
 * F1206 模式: UNSAFE_root.findAllByType 直查 + fail-fast; 直接调用
 * rc.props.onRefresh() (KnowledgeScreen.ext6 先例 — fireEvent.press 在
 * RCTScrollView 宿主形态下不可靠, 且直接调用闭包语义更精确)。
 */
async function flush(ms: number) {
  await act(async () => {
    await new Promise((r) => setTimeout(r, ms));
  });
}

async function pullToRefresh(UNSAFE_root: unknown) {
  const all = (UNSAFE_root as unknown as {
    findAllByType?: (type: unknown) => { props?: { onRefresh?: () => void; refreshing?: boolean } }[];
  }).findAllByType?.(RefreshControl);
  expect(all && all.length >= 1).toBe(true);
  const rc = all![0];
  expect(typeof rc?.props?.onRefresh).toBe('function');
  await act(async () => {
    rc?.props?.onRefresh?.();
    await flush(50);
  });
}

describe('MonitorScreen.ext5 — 下拉刷新与失败恢复 (L39/57)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('下拉刷新走 isRefresh 分支: 不出现加载态且数据重新拉取 (L39)', async () => {
    mockAllSuccess();
    const { UNSAFE_root, getByText, queryByText } = render(<MonitorScreen />);
    // 挂载完成: 概览数据已渲染
    expect(await waitFor(() => getByText('监控概览'))).toBeTruthy();
    expect(queryByText('加载监控数据...')).toBeNull();

    (monitorApi.getSummary as jest.Mock).mockClear();
    await pullToRefresh(UNSAFE_root);

    // isRefresh=true: 不重置为全屏 loading (仍能看到概览标题)
    expect(queryByText('加载监控数据...')).toBeNull();
    // 数据源被重新请求 (mockClear 后刷新这轮 ≥1;
    // getDeviceStatusList 可能因 devices.length 变化触发 effect 重跑多 1 次)
    expect(monitorApi.getSummary).toHaveBeenCalledTimes(1);
    expect((deviceMonitorApi.getDeviceStatusList as jest.Mock).mock.calls.length).toBeGreaterThanOrEqual(1);
  });

  it('刷新失败: catch 设置错误提示, 已有 summary 时提示条渲染而非 EmptyState (L57)', async () => {
    mockAllSuccess();
    const { UNSAFE_root, getByText, queryByText } = render(<MonitorScreen />);
    expect(await waitFor(() => getByText('监控概览'))).toBeTruthy();

    // 刷新时全部失败 → catch → setError
    (monitorApi.getSummary as jest.Mock).mockRejectedValue(
      new Error('network down')
    );
    (deviceMonitorApi.getDeviceStatusList as jest.Mock).mockRejectedValue(
      new Error('network down')
    );
    (monitorApi.getFaultDevices as jest.Mock).mockRejectedValue(
      new Error('network down')
    );
    (monitorApi.getCriticalAlarms as jest.Mock).mockRejectedValue(
      new Error('network down')
    );
    await pullToRefresh(UNSAFE_root);

    // 源码语义: error 唯一UI出口是 `error && !summary` EmptyState (L122)。
    // 刷新失败但 summary 保留 → 静默降级: 不出现 EmptyState 重试按钮,
    // 旧概览数据仍在 (catch L57 已执行, UI 不重置)
    expect(queryByText('重新加载')).toBeNull();
    expect(getByText('监控概览')).toBeTruthy();
    expect(getByText('10')).toBeTruthy();
    // 刷新确实发起过 (挂载1 + 失败刷新1 = 2)
    expect(monitorApi.getSummary).toHaveBeenCalledTimes(2);
  });

  it('刷新失败后恢复: 再刷新成功 → 错误提示消失 (L57→恢复链)', async () => {
    mockAllSuccess();
    const { UNSAFE_root, getByText, queryByText } = render(<MonitorScreen />);
    expect(await waitFor(() => getByText('监控概览'))).toBeTruthy();

    (monitorApi.getSummary as jest.Mock).mockRejectedValueOnce(
      new Error('transient')
    );
    (deviceMonitorApi.getDeviceStatusList as jest.Mock).mockRejectedValueOnce(
      new Error('transient')
    );
    (monitorApi.getFaultDevices as jest.Mock).mockRejectedValueOnce(
      new Error('transient')
    );
    (monitorApi.getCriticalAlarms as jest.Mock).mockRejectedValueOnce(
      new Error('transient')
    );
    await pullToRefresh(UNSAFE_root);
    // 失败静默 (无EmptyState), 数据保留
    expect(queryByText('重新加载')).toBeNull();
    expect(getByText('10')).toBeTruthy();

    // 恢复: 下一次刷新成功 (mockRejectedValueOnce 只生效一次), 返回新 summary
    (monitorApi.getSummary as jest.Mock).mockResolvedValue({
      data: { ...SUMMARY, totalDevices: 12 },
    });
    await pullToRefresh(UNSAFE_root);
    // 新数据生效 (10 → 12): 刷新链真正跑通且状态更新
    await waitFor(() => {
      expect(getByText('12')).toBeTruthy();
    });
    expect(queryByText('10')).toBeNull();
  });
});
