import { renderHook, act, waitFor } from '@testing-library/react-native';
import { energyApi } from '../../services/api';
import { useEnergy } from '../useEnergy';
import { EnergySummary } from '../../types';

// 可控 useIsFocused: jest.setup 全局 mock 恒 true, 此处局部覆盖以测 false 分支
let mockIsFocused = true;
jest.mock('@react-navigation/native', () => ({
  useIsFocused: () => mockIsFocused,
}));

jest.mock('../../services/api', () => ({
  energyApi: {
    getSummary: jest.fn(),
  },
}));

const mockSummary: EnergySummary = {
  period: '2026-08',
  days: 30,
  pvGeneration: 15230.5,
  chargingAmount: 8200.3,
  dischargeAmount: 4500.0,
  pvRevenue: 7600.25,
  chargingRevenue: 16400.6,
  dischargeRevenue: 2250.0,
  totalRevenue: 26250.85,
  yoy: {
    pvGenerationYoY: 0.15,
    chargingAmountYoY: -0.08,
    dischargeAmountYoY: 0.12,
    totalRevenueYoY: 0.22,
  },
  priceInfo: {
    feedInTariff: 0.45,
    chargingPrice: 1.20,
    dischargePrice: 0.80,
  },
} as never;

describe('useEnergy.ext — isFocused=false branch (L48)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockIsFocused = true;
  });

  it('does not fetch when isFocused is false', async () => {
    mockIsFocused = false;
    (energyApi.getSummary as jest.Mock).mockResolvedValue({ data: mockSummary });

    const { result } = renderHook(() => useEnergy());

    // effect 直接走 else(no-op), 不发起请求, loading 停留在初始 true
    expect(result.current.loading).toBe(true);
    expect(result.current.summary).toBeNull();

    // 冲刷微任务队列, 确认没有异步 fetch 被排队
    await act(async () => {
      await Promise.resolve();
    });
    expect(energyApi.getSummary).not.toHaveBeenCalled();
  });

  it('refetches when focus transitions false → true', async () => {
    mockIsFocused = false;
    (energyApi.getSummary as jest.Mock).mockResolvedValue({ data: mockSummary });

    const { result, rerender } = renderHook(() => useEnergy());
    await act(async () => {
      await Promise.resolve();
    });
    expect(energyApi.getSummary).not.toHaveBeenCalled();

    // 回焦: effect 依赖 isFocused 变化 → 重新执行 → 发起 fetch
    mockIsFocused = true;
    rerender();

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
    expect(energyApi.getSummary).toHaveBeenCalledTimes(1);
    expect(result.current.summary).toEqual(mockSummary);
  });
});
