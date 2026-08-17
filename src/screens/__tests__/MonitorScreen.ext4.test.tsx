/**
 * F1209: MonitorScreen 轮询 effect 覆盖补充 (lines 105-107)
 * 既有四套件未覆盖 activeTab='devices' && devices.length>0 时的 10s interval
 * 轮询链。方案: 真实 timers + jest.spyOn 全局 setInterval 受控捕获 —
 * 源码注册的 interval 回调由测试显式触发; 挂载期 Promise.resolve().then
 * 首拉走真实链路。
 * 注意: spyOn(global.setInterval) 会拦截 RNTL waitFor 内部计时器导致其永不
 * 重查（probe2 实证 waitFor 挂死），故本套件全部用 microtask flush 轮询替代
 * waitFor/findBy*。
 */
import { render, fireEvent, act } from '@testing-library/react-native';
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

// 受控 interval: 捕获源码注册的回调但不真正计时
let capturedIntervalCb: (() => void) | null = null;
const spySetInterval = jest
  .spyOn(global, 'setInterval')
  .mockImplementation(((cb: () => void) => {
    capturedIntervalCb = cb;
    // 必须返回 truthy: 源码 cleanup 用 `if (refreshTimer.current)` 守卫,
    // 返回 0 (falsy) 会让 clearInterval 被跳过
    return 1 as unknown as ReturnType<typeof setInterval>;
  }) as typeof setInterval);
const spyClearInterval = jest
  .spyOn(global, 'clearInterval')
  .mockImplementation(() => undefined);

// microtask flush 轮询等待条件（替代被 spy 影响的 waitFor）
async function until(cond: () => boolean, maxLoops = 200) {
  for (let i = 0; i < maxLoops; i++) {
    if (cond()) return;
    await act(async () => {
      await Promise.resolve();
    });
  }
  expect(cond()).toBe(true);
}

describe('MonitorScreen.ext4 — 轮询 effect (10s interval on devices tab)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    capturedIntervalCb = null;
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
  });

  afterAll(() => {
    spySetInterval.mockRestore();
    spyClearInterval.mockRestore();
  });

  it('首拉立即执行 + 周期回调第二次拉取 (interval 真实注册与触发)', async () => {
    render(<MonitorScreen />);

    // 初始 fetchData 完成 + 挂载期首拉 (Promise.resolve().then 链) 均真实走通
    await until(
      () =>
        (deviceMonitorApi.getRealtimeOverview as jest.Mock).mock.calls.length >=
        1
    );
    // effect 已注册 10s interval (受控捕获)
    expect(capturedIntervalCb).not.toBeNull();
    expect(spySetInterval).toHaveBeenCalledWith(expect.any(Function), 10_000);

    // 触发周期回调 → 第二次拉取
    await act(async () => {
      capturedIntervalCb?.();
      await Promise.resolve();
    });
    await until(
      () =>
        (deviceMonitorApi.getRealtimeOverview as jest.Mock).mock.calls.length >=
        2
    );
  });

  it('卸载后 interval 清理 (clearInterval 被调用)', async () => {
    const { unmount } = render(<MonitorScreen />);
    await until(
      () =>
        (deviceMonitorApi.getRealtimeOverview as jest.Mock).mock.calls.length >=
        1
    );
    // interval 已注册 (refreshTimer.current 非 null) — 卸载时应走 clearInterval
    expect(capturedIntervalCb).not.toBeNull();

    (spyClearInterval as jest.Mock).mockClear();
    unmount();
    expect(spyClearInterval).toHaveBeenCalled();
  });

  it('切到 faults tab 后轮询停止 (清理旧 interval, faults tab 不重建)', async () => {
    const { getByText } = render(<MonitorScreen />);
    await until(
      () =>
        (deviceMonitorApi.getRealtimeOverview as jest.Mock).mock.calls.length >=
        1
    );
    expect(capturedIntervalCb).not.toBeNull();

    // 切到 faults: activeTab !== 'devices' → effect 清理且不重建
    capturedIntervalCb = null;
    (spySetInterval as jest.Mock).mockClear();
    // fireEvent.press 自动从 Text 冒泡到可按压宿主 (TouchableOpacity) —
    // 手工树遍历读不到 fiber 元素对象里的嵌套文本 (probe 实证 N50 链)
    fireEvent.press(getByText('故障设备'));
    await act(async () => {
      await Promise.resolve();
    });

    // faults tab 下 10s interval 不再注册
    expect(spySetInterval).not.toHaveBeenCalled();
    expect(capturedIntervalCb).toBeNull();
  });
});
