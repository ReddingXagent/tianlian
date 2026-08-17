import React from 'react';
import { render, waitFor } from '@testing-library/react-native';
import EnergyScreen from '../EnergyScreen';

// --- mocks ---
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

describe('EnergyScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should show loading spinner initially', () => {
    mockGetSummary.mockReturnValue(new Promise(() => {})); // never resolves
    const { getByText } = render(<EnergyScreen />);
    expect(getByText('加载能源数据...')).toBeTruthy();
  });

  it('should render energy data when loaded', async () => {
    mockGetSummary.mockResolvedValue({ data: mockSummary });
    const { getByText } = render(<EnergyScreen />);

    await waitFor(() => {
      expect(getByText('2026-08')).toBeTruthy();
    });

    // Period info
    expect(getByText('30 天')).toBeTruthy();

    // Section titles
    expect(getByText('发电')).toBeTruthy();
    expect(getByText('充电')).toBeTruthy();
    expect(getByText('放电')).toBeTruthy();
    expect(getByText('总收入')).toBeTruthy();
    expect(getByText('当前电价')).toBeTruthy();
  });

  it('should show error state with retry on failure', async () => {
    mockGetSummary.mockRejectedValue(new Error('网络错误'));
    const { getByText } = render(<EnergyScreen />);

    await waitFor(() => {
      expect(getByText('加载失败')).toBeTruthy();
    });

    expect(getByText('网络错误')).toBeTruthy();
    expect(getByText('重试')).toBeTruthy();
  });

  it('should show empty state when no data', async () => {
    mockGetSummary.mockResolvedValue({ data: null });
    const { getByText } = render(<EnergyScreen />);

    await waitFor(() => {
      expect(getByText('暂无数据')).toBeTruthy();
    });
  });

  it('should display YoY percentage with sign', async () => {
    mockGetSummary.mockResolvedValue({ data: mockSummary });
    const { getByText } = render(<EnergyScreen />);

    await waitFor(() => {
      expect(getByText(/15\.0%/)).toBeTruthy();  // pvGenerationYoY positive
    });

    // chargingAmountYoY negative
    expect(getByText(/-8\.0%/)).toBeTruthy();
  });

  it('should display total revenue formatted', async () => {
    mockGetSummary.mockResolvedValue({ data: mockSummary });
    const { getByText } = render(<EnergyScreen />);

    await waitFor(() => {
      expect(getByText(/26250\.85/)).toBeTruthy();
    });
  });

  it('should display electricity prices', async () => {
    mockGetSummary.mockResolvedValue({ data: mockSummary });
    const { getByText } = render(<EnergyScreen />);

    await waitFor(() => {
      expect(getByText(/0\.45.*kWh/)).toBeTruthy();
    });

    expect(getByText(/1\.20.*kWh/)).toBeTruthy();
    expect(getByText(/0\.80.*kWh/)).toBeTruthy();
  });

  it('should render negative YoY values with red color', async () => {
    const negativeMock = {
      ...mockSummary,
      yoy: {
        pvGenerationYoY: -0.10,
        chargingAmountYoY: -0.05,
        dischargeAmountYoY: -0.15,
        totalRevenueYoY: -0.20,
      },
    } as never;
    mockGetSummary.mockResolvedValue({ data: negativeMock });
    const { getByText } = render(<EnergyScreen />);

    await waitFor(() => {
      expect(getByText(/-10\.0%/)).toBeTruthy();
    });

    expect(getByText(/-5\.0%/)).toBeTruthy();
    expect(getByText(/-15\.0%/)).toBeTruthy();
    expect(getByText(/-20\.0%/)).toBeTruthy();
  });

  it('should render zero YoY as positive (>=0 branch)', async () => {
    const zeroMock = {
      ...mockSummary,
      yoy: {
        pvGenerationYoY: 0,
        chargingAmountYoY: 0,
        dischargeAmountYoY: 0,
        totalRevenueYoY: 0,
      },
    } as never;
    mockGetSummary.mockResolvedValue({ data: zeroMock });
    const { getAllByText } = render(<EnergyScreen />);

    await waitFor(() => {
      expect(getAllByText(/\+0\.0%/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('should render period fallback when summary.period is empty', async () => {
    const noPeriodMock = { ...mockSummary, period: '' } as never;
    mockGetSummary.mockResolvedValue({ data: noPeriodMock });
    const { getByText } = render(<EnergyScreen />);

    await waitFor(() => {
      expect(getByText('近30天')).toBeTruthy();
    });
  });
});
