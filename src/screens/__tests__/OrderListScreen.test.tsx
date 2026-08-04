import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import OrderListScreen from '../OrderListScreen';

// --- mocks ---
const mockOrders = [
  {
    id: 1,
    orderNo: 'ORD-001',
    userId: 1,
    stationId: 1,
    stationName: '测试充电站',
    chargerId: 1,
    chargerName: '1号桩',
    status: 'charging',
    startTime: '2025-01-01T10:00:00Z',
    amount: 0,
    paymentStatus: 'pending',
    energy: 0,
    duration: 0,
  },
  {
    id: 2,
    orderNo: 'ORD-002',
    userId: 1,
    stationId: 2,
    stationName: '另一个站',
    chargerId: 3,
    chargerName: '3号桩',
    status: 'completed',
    startTime: '2025-01-01T08:00:00Z',
    endTime: '2025-01-01T09:00:00Z',
    amount: 25.5,
    paymentStatus: 'paid',
    energy: 20.5,
    duration: 3600,
  },
];

const mockFetchOrders = jest.fn().mockResolvedValue(undefined);

// 动态store态: 错误路径测试需切换 orders/error (F221)
let mockOrdersState = mockOrders;
let mockErrorState: string | null = null;

jest.mock('../../store/orderStore', () => ({
  useOrderStore: () => ({
    orders: mockOrdersState,
    loading: false,
    error: mockErrorState,
    fetchOrders: mockFetchOrders,
    loadMoreOrders: jest.fn(),
    hasMore: false,
    loadingMore: false,
  }),
}));

const mockNavigate = jest.fn();
let mockFocused = true;
jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: mockNavigate }),
  useIsFocused: () => mockFocused,
}));

jest.mock('../../components/StatusBadge', () => 'StatusBadge');
jest.mock('../../components/LoadingSpinner', () => 'LoadingSpinner');
// EmptyState用真组件: F221错误路径需断言title/重试按钮文案与点击

describe('OrderListScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFocused = true;
    mockOrdersState = mockOrders;
    mockErrorState = null;
  });

  const renderScreen = () =>
    render(
      <SafeAreaProvider>
        <OrderListScreen />
      </SafeAreaProvider>
    );

  it('renders filter labels', () => {
    const { getByText } = renderScreen();
    expect(getByText('全部')).toBeTruthy();
    expect(getByText('充电中')).toBeTruthy();
    expect(getByText('已完成')).toBeTruthy();
    expect(getByText('未支付')).toBeTruthy();
  });

  it('renders order numbers with prefix', () => {
    const { getByText } = renderScreen();
    expect(getByText('订单号: ORD-001')).toBeTruthy();
    expect(getByText('订单号: ORD-002')).toBeTruthy();
  });

  it('renders station names in orders', () => {
    const { getByText } = renderScreen();
    expect(getByText('测试充电站')).toBeTruthy();
    expect(getByText('另一个站')).toBeTruthy();
  });

  it('calls fetchOrders on mount', () => {
    renderScreen();
    expect(mockFetchOrders).toHaveBeenCalled();
  });

  it('refetches when tab regains focus (回焦刷新)', () => {
    const utils = renderScreen();
    expect(mockFetchOrders).toHaveBeenCalledTimes(1);

    mockFocused = false;
    utils.rerender(
      <SafeAreaProvider>
        <OrderListScreen />
      </SafeAreaProvider>
    );
    expect(mockFetchOrders).toHaveBeenCalledTimes(1);

    mockFocused = true;
    utils.rerender(
      <SafeAreaProvider>
        <OrderListScreen />
      </SafeAreaProvider>
    );
    expect(mockFetchOrders).toHaveBeenCalledTimes(2);
  });

  // --- F221: 首屏拉取失败不能伪装成"暂无订单" ---
  it('首屏拉取失败且无订单时显示加载失败+重试(而非"暂无订单")', () => {
    mockOrdersState = [];
    mockErrorState = '网络异常';
    const { getByText, queryByText } = renderScreen();
    expect(getByText('加载失败')).toBeTruthy();
    expect(getByText('网络异常')).toBeTruthy();
    expect(getByText('重试')).toBeTruthy();
    expect(queryByText('暂无订单')).toBeNull();
  });

  it('点击重试重新拉取订单列表', () => {
    mockOrdersState = [];
    mockErrorState = '网络异常';
    const { getByText } = renderScreen();
    expect(mockFetchOrders).toHaveBeenCalledTimes(1);

    fireEvent.press(getByText('重试'));
    expect(mockFetchOrders).toHaveBeenCalledTimes(2);
    expect(mockFetchOrders).toHaveBeenLastCalledWith({ status: undefined });
  });

  it('有订单时拉取失败保留列表可见(不整屏切错误页)', () => {
    mockErrorState = '刷新失败';
    const { getByText, queryByText } = renderScreen();
    expect(getByText('订单号: ORD-001')).toBeTruthy();
    expect(getByText('订单号: ORD-002')).toBeTruthy();
    expect(queryByText('加载失败')).toBeNull();
  });
});
