/**
 * F1212: MonitorScreen L65 补测 — devices 空时轮询不注册
 * L65 fetchRealtimeMetrics 开头 `if (devices.length === 0) return;` 与
 * 轮询 effect 的 `devices.length > 0` 双重守卫: 空devices挂载时两个入口都挡。
 * 手法: mock空items挂载 → fail-fast 断言 setInterval 从未注册 +
 * getRealtimeOverview 零调用 (fetchRealtimeMetrics 唯一消费方)。
 * 注: 初版设计“捕获旧cb后清空再触发”不可行 — 受控spy下新注册覆盖引用,
 * 改为直接验证空态分支语义 (与源码守卫意图一致)。
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

let intervalCb: (() => void) | null = null;
jest
  .spyOn(global, 'setInterval')
  .mockImplementation(
    ((cb: () => void) => {
      intervalCb = cb;
      return 1 as unknown as ReturnType<typeof setInterval>;
    }) as typeof setInterval,
  );
jest.spyOn(global, 'clearInterval').mockImplementation(() => undefined);

const SUMMARY = {
  totalDevices: 10,
  onlineDevices: 7,
  faultDevices: 2,
  criticalAlarms: 1,
};
const OVERVIEW = {
  totalPower: 1,
  powerTrend: 1,
  todayGeneration: 1,
  todayConsumption: 1,
  gridImport: 1,
  gridExport: 1,
  efficiency: 1,
  updateTime: '',
  devices: [],
};

function mockAll(devices: unknown[]) {
  (monitorApi.getSummary as jest.Mock).mockResolvedValue({ data: SUMMARY });
  (deviceMonitorApi.getDeviceStatusList as jest.Mock).mockResolvedValue({
    data: { items: devices, total: devices.length },
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

async function until(cond: () => boolean, maxLoops = 200) {
  for (let i = 0; i < maxLoops; i++) {
    if (cond()) return;
    await act(async () => {
      await Promise.resolve();
    });
  }
  expect(cond()).toBe(true);
}

describe('MonitorScreen.ext8 — L65 devices 空早退守卫', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    intervalCb = null;
  });

  it('L65 路径: 空devices挂载 → 轮询不注册 → cb空(严格断言)', async () => {
    mockAll([]);
    const { unmount } = render(<MonitorScreen />);
    // 等挂载 fetch 完成: devices=[] → effect 分支 0>0 为假 → setInterval 从未注册
    await until(
      () => (monitorApi.getSummary as jest.Mock).mock.calls.length >= 1,
    );
    for (let i = 0; i < 20; i++) {
      await act(async () => {
        await Promise.resolve();
      });
    }
    // fail-fast: 空设备下 interval 绝不注册 (activeTab='devices' 但 length=0)
    expect(intervalCb).toBeNull();
    // fetchRealtimeMetrics 若被调则 overview 应有计数 — 空挂载下必须为 0,
    // 因为唯一入口(轮询effect分支/interval回调)都被 0>0 守卫挡住
    expect(
      (deviceMonitorApi.getRealtimeOverview as jest.Mock).mock.calls.length,
    ).toBe(0);
    unmount();
  });
});
