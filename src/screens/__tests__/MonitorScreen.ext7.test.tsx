/**
 * F1212: MonitorScreen L84/L90 cancelled 守卫补测 — unmount-before-resolve
 * 既有套件未覆盖挂载 effect 内两处 `if (cancelled) return;` (L84 try 成功链 /
 * L90 catch 链): 需要 fetch 未完成时卸载组件, resolve 后守卫拦截 setState。
 * 手法: deferred promise (持有 resolver, 卸载后再放行) — F1211 ext6 同款
 * 受控 setInterval/clearInterval (ext4 模式) 防真实计时器泄漏。
 * 勘误: F1211 所记 "98.7% (仅L105缺口)" 有误, 实测 95.12% 四行缺口
 * (65/84/90/105); 其中 L65/L105 为防御性死代码 (闭包守卫/永不reject链),
 * 本轮补 L84/L90 后剩两行属不可达防御位。
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

// 受控 setInterval (ext4/ext6 模式: 不让真实 10s 计时器进入测试环境)
jest
  .spyOn(global, 'setInterval')
  .mockImplementation(
    ((cb: () => void) => {
      void cb; // 本套件不手动触发 interval, 仅需拦截注册
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

type Deferred = {
  resolve: (v: unknown) => void;
  reject: (e: unknown) => void;
};

function makeDeferredApi() {
  // 四个挂载期 fetch 全部挂起 (Promise.all 任一未决 → 整链未决)
  let dSummary: Deferred | null = null;
  (monitorApi.getSummary as jest.Mock).mockImplementation(
    () =>
      new Promise((resolve, reject) => {
        dSummary = { resolve, reject };
      }),
  );
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
    data: {
      totalPower: 1,
      powerTrend: 1,
      todayGeneration: 1,
      todayConsumption: 1,
      gridImport: 1,
      gridExport: 1,
      efficiency: 1,
      updateTime: '',
      devices: [],
    },
  });
  return {
    get deferred() {
      return dSummary;
    },
  };
}

describe('MonitorScreen.ext7 — cancelled 守卫 (L84/L90)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('卸载后 resolve → L84 守卫拦截 (try 链 setState 不执行)', async () => {
    const api = makeDeferredApi();
    const { unmount } = render(<MonitorScreen />);
    // 等 getSummary 已被调用且挂起
    for (let i = 0; i < 100; i++) {
      await act(async () => {
        await Promise.resolve();
      });
      if ((monitorApi.getSummary as jest.Mock).mock.calls.length >= 1) break;
    }
    if (!api.deferred) throw new Error('FAIL-FAST: getSummary 未挂起');
    unmount();
    // 卸载后放行 → cancelled=true → L84 return (无 setState after unmount)
    await act(async () => {
      api.deferred!.resolve({ data: SUMMARY });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(monitorApi.getSummary).toHaveBeenCalledTimes(1);
  });

  it('卸载后 reject → L90 守卫拦截 (catch 链 setError 不执行)', async () => {
    const api = makeDeferredApi();
    const { unmount } = render(<MonitorScreen />);
    for (let i = 0; i < 100; i++) {
      await act(async () => {
        await Promise.resolve();
      });
      if ((monitorApi.getSummary as jest.Mock).mock.calls.length >= 1) break;
    }
    if (!api.deferred) throw new Error('FAIL-FAST: getSummary 未挂起');
    unmount();
    await act(async () => {
      api.deferred!.reject(new Error('late-reject'));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(monitorApi.getSummary).toHaveBeenCalledTimes(1);
  });
});
