/**
 * F1211: MonitorScreen L105 补测 — devices tab 轮询 interval 回调
 * 既有套件 (含 ext5) 只在概览 tab 断言, 未进入 activeTab==='devices' 的
 * 轮询 effect 内 setInterval 回调体 (L104-106: void fetchRealtimeMetrics())。
 * 手法: 受控 setInterval (ext4 模式) + tab 切换 (ext.test fireEvent.press
 * getByText('故障设备') 先例), 触发后锚定 getRealtimeOverview 调用次数增量。
 * 注意: spyOn(global.setInterval) 拦截 RNTL waitFor 内部计时器会导致挂死
 * (ext4 probe2 实证), 故挂载期等待全部用 microtask flush 轮询替代 waitFor。
 */
import { render, act } from '@testing-library/react-native';
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

// 受控 setInterval: 捕获回调供 act 内手动触发 (ext4 模式, 不用 fake timers)
let intervalCb: (() => void) | null = null;
jest
  .spyOn(global, 'setInterval')
  .mockImplementation(((cb: () => void) => {
    intervalCb = cb;
    // 必须返回 truthy: 源码 cleanup 用 `if (refreshTimer.current)` 守卫
    return 1 as unknown as ReturnType<typeof setInterval>;
  }) as typeof setInterval);
// clearInterval 同步受控 (ext4 模式: 防真实 id=1 被清导致 RNTL 内部计时器互串)
jest
  .spyOn(global, 'clearInterval')
  .mockImplementation(() => undefined);

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

// microtask flush 轮询等待条件 (ext4 模式: 替代被 spy 影响的 waitFor)
async function until(cond: () => boolean, maxLoops = 200) {
  for (let i = 0; i < maxLoops; i++) {
    if (cond()) return;
    await act(async () => {
      await Promise.resolve();
    });
  }
  expect(cond()).toBe(true);
}

describe('MonitorScreen.ext6 — devices tab 轮询 interval (L105)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    intervalCb = null;
    mockAllSuccess();
  });

  it('interval 回调触发 getRealtimeOverview 增量调用 (L104-106)', async () => {
    render(<MonitorScreen />);
    // 挂载期初始 fetchData + 首拉 (Promise.resolve().then 链) 真实走通
    // (ext4 模式: until microtask 轮询, 不用 waitFor — spyOn 后挂死实证)
    await until(
      () =>
        (deviceMonitorApi.getRealtimeOverview as jest.Mock).mock.calls.length >=
        1,
    );

    const before = (deviceMonitorApi.getRealtimeOverview as jest.Mock).mock.calls
      .length;
    // fail-fast: 默认 tab 即 devices 且 devices.length>0 → interval 已注册
    // (F1206 模式, 找不到测试变红而非静默通过)
    expect(intervalCb).not.toBeNull();

    // 触发 interval 回调 (L105: void fetchRealtimeMetrics())
    await act(async () => {
      intervalCb!();
      await Promise.resolve();
    });
    expect(
      (deviceMonitorApi.getRealtimeOverview as jest.Mock).mock.calls.length,
    ).toBe(before + 1);
  });
});
