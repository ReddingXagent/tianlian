import React from 'react';
import { render, waitFor, fireEvent, act } from '@testing-library/react-native';
import { ScrollView } from 'react-native';
import EnergyScreen from '../EnergyScreen';

const mockGetSummary = jest.fn();

jest.mock('../../services/api', () => ({
  energyApi: {
    getSummary: (...args: unknown[]) => mockGetSummary(...args),
  },
}));

jest.mock('@react-navigation/native', () => ({
  useIsFocused: () => true,
}));

const mockSummary = {
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

describe('EnergyScreen coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should call refresh when error retry button pressed', async () => {
    mockGetSummary.mockRejectedValueOnce(new Error('网络错误')).mockResolvedValueOnce({ data: mockSummary });
    const { getByText } = render(<EnergyScreen />);

    await waitFor(() => {
      expect(getByText('加载失败')).toBeTruthy();
    });

    fireEvent.press(getByText('重试'));
    expect(mockGetSummary).toHaveBeenCalledTimes(2);
  });

  it('should call refresh when empty state refresh button pressed', async () => {
    mockGetSummary.mockResolvedValueOnce({ data: null });
    const { getByText } = render(<EnergyScreen />);

    await waitFor(() => {
      expect(getByText('暂无数据')).toBeTruthy();
    });

    fireEvent.press(getByText('刷新'));
    expect(mockGetSummary).toHaveBeenCalledTimes(2);
  });

  it('should trigger handleRefresh via RefreshControl onRefresh', async () => {
    mockGetSummary.mockResolvedValue({ data: mockSummary });
    const { UNSAFE_root } = render(<EnergyScreen />);

    await waitFor(() => {
      expect(UNSAFE_root.findByType(ScrollView)).toBeTruthy();
    });

    const scrollView = UNSAFE_root.findByType(ScrollView);
    const refreshControl = scrollView.props.refreshControl;

    expect(refreshControl).toBeTruthy();
    await act(async () => {
      refreshControl.props.onRefresh();
    });

    expect(mockGetSummary).toHaveBeenCalledTimes(2);
  });
});
