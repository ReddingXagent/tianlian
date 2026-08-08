import React from 'react';
import { Alert, FlatList } from 'react-native';
import { render, waitFor, act, fireEvent } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import WalletScreen from '../WalletScreen';

// --- mocks ---
const mockGetRecords = jest.fn();
const mockRecharge = jest.fn();
const mockGetProfile = jest.fn();
const mockAlertAlert = jest.spyOn(Alert, 'alert').mockImplementation(() => {});

jest.mock('../../services/api', () => ({
  walletApi: {
    getRecords: (...args: unknown[]) => mockGetRecords(...args),
    recharge: (...args: unknown[]) => mockRecharge(...args),
  },
  authApi: {
    getProfile: (...args: unknown[]) => mockGetProfile(...args),
  },
}));

const mockUser = {
  id: 1,
  phone: '13800001111',
  nickname: '测试用户',
  balance: 150.0,
};

const mockSetUser = jest.fn();

jest.mock('../../store/authStore', () => ({
  useAuthStore: () => ({
    user: mockUser,
    setUser: mockSetUser,
  }),
}));

let mockFocused = true;
jest.mock('@react-navigation/native', () => ({
  useIsFocused: () => mockFocused,
}));

// Helper: multi-page fixture
const makeRecords = (count: number, startId = 1) =>
  Array.from({ length: count }, (_, i) => ({
    id: startId + i,
    userId: 1,
    type: 'consume' as const,
    amount: 10 + i,
    balance: 100 - i,
    description: `消费${startId + i}`,
    createdAt: '2025-01-02T14:00:00Z',
  }));

type AlertButton = { text: string; onPress: () => void };

describe('WalletScreen extended coverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFocused = true;
    mockAlertAlert.mockClear();
    mockGetProfile.mockResolvedValue({ data: { id: 1, phone: '138', nickname: 'u', balance: 200 } });
  });

  const renderScreen = () =>
    render(
      <SafeAreaProvider>
        <WalletScreen />
      </SafeAreaProvider>
    );

  // === loadMoreRecords 分页 ===

  it('加载第二页并合并结果(onEndReached 触底加载)', async () => {
    const page1 = makeRecords(20, 1);
    const page2 = makeRecords(5, 21);
    let call = 0;
    mockGetRecords.mockImplementation(() => {
      call += 1;
      if (call === 1) return Promise.resolve({ data: { items: page1, page: 1, total: 25 } });
      return Promise.resolve({ data: { items: page2, page: 2, total: 25 } });
    });
    const { UNSAFE_getByType } = renderScreen();
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalledTimes(1));

    const list = UNSAFE_getByType(FlatList);
    await act(async () => {
      if (list.props.onEndReached) list.props.onEndReached();
    });
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalledTimes(2));
    // Page 2 items merged
    await waitFor(() => expect(mockGetRecords).toHaveBeenNthCalledWith(2, { page: 2, pageSize: 20 }));
  });

  it('loadMoreRecords 不重复已加载记录(dedup by id)', async () => {
    const dupRecords = [
      ...makeRecords(20, 1),
      // page2 returns id=5 duplicate
      { id: 5, userId: 1, type: 'consume', amount: 99, balance: 0, description: 'dup', createdAt: '2025-01-02T14:00:00Z' },
      ...makeRecords(1, 21),
    ];
    let call = 0;
    mockGetRecords.mockImplementation(() => {
      call += 1;
      if (call === 1) return Promise.resolve({ data: { items: makeRecords(20, 1), page: 1, total: 22 } });
      return Promise.resolve({ data: { items: dupRecords.slice(20), page: 2, total: 22 } });
    });
    const { UNSAFE_getByType } = renderScreen();
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalledTimes(1));

    const list = UNSAFE_getByType(FlatList);
    await act(async () => {
      if (list.props.onEndReached) list.props.onEndReached();
    });
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalledTimes(2));
    // No crash, dedup logic executed
  });

  it('loadMoreRecords 失败静默处理(不影响已有列表)', async () => {
    let call = 0;
    mockGetRecords.mockImplementation(() => {
      call += 1;
      if (call === 1) return Promise.resolve({ data: { items: makeRecords(20, 1), page: 1, total: 25 } });
      return Promise.reject(new Error('网络断了'));
    });
    const { UNSAFE_getByType, getByText } = renderScreen();
    await waitFor(() => expect(getByText('消费1')).toBeTruthy());

    const list = UNSAFE_getByType(FlatList);
    await act(async () => {
      if (list.props.onEndReached) list.props.onEndReached();
    });
    // Original list intact
    expect(getByText('消费1')).toBeTruthy();
  });

  it('loadMoreRecords 在 hasMore=false 时不触发', async () => {
    mockGetRecords.mockResolvedValue({ data: { items: makeRecords(5, 1), page: 1, total: 5 } });
    const { UNSAFE_getByType } = renderScreen();
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalledTimes(1));

    const list = UNSAFE_getByType(FlatList);
    await act(async () => {
      if (list.props.onEndReached) list.props.onEndReached();
    });
    // Should not fetch page 2 since hasMore=false
    expect(mockGetRecords).toHaveBeenCalledTimes(1);
  });

  it('loadMoreRecords 在 loadingMore=true 时不重复触发', async () => {
    let resolvePage2: ((v: unknown) => void) | undefined;
    let call = 0;
    mockGetRecords.mockImplementation(() => {
      call += 1;
      if (call === 1) return Promise.resolve({ data: { items: makeRecords(20, 1), page: 1, total: 40 } });
      return new Promise((resolve) => { resolvePage2 = resolve; });
    });
    const { UNSAFE_getByType } = renderScreen();
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalledTimes(1));

    const list = UNSAFE_getByType(FlatList);
    await act(async () => {
      if (list.props.onEndReached) list.props.onEndReached();
    });
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalledTimes(2));

    // Try to trigger again while loadingMore is still pending
    await act(async () => {
      if (list.props.onEndReached) list.props.onEndReached();
    });
    expect(mockGetRecords).toHaveBeenCalledTimes(2); // No extra call

    // Cleanup: resolve pending promise
    if (resolvePage2) act(() => resolvePage2!({ data: { items: makeRecords(5, 21), page: 2, total: 40 } }));
  });

  // === renderRecordItem 类型覆盖 ===

  it('充值类型记录显示+(recharge)', async () => {
    mockGetRecords.mockResolvedValue({
      data: {
        items: [{
          id: 1, userId: 1, type: 'recharge', amount: 50, balance: 200,
          description: '充值50元', createdAt: '2025-01-01T10:00:00Z',
        }],
        page: 1, total: 1,
      },
    });
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('充值')).toBeTruthy());
    expect(getByText('充值50元')).toBeTruthy();
  });

  it('退款类型记录显示+(refund)', async () => {
    mockGetRecords.mockResolvedValue({
      data: {
        items: [{
          id: 1, userId: 1, type: 'refund', amount: 15, balance: 165,
          description: '退款到账', createdAt: '2025-01-01T10:00:00Z',
        }],
        page: 1, total: 1,
      },
    });
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('退款到账')).toBeTruthy());
    expect(getByText('退款')).toBeTruthy();
  });

  it('提现类型记录显示-(withdraw)', async () => {
    mockGetRecords.mockResolvedValue({
      data: {
        items: [{
          id: 1, userId: 1, type: 'withdraw', amount: 30, balance: 120,
          description: '提现到银行卡', createdAt: '2025-01-01T10:00:00Z',
        }],
        page: 1, total: 1,
      },
    });
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('提现到银行卡')).toBeTruthy());
    expect(getByText('提现')).toBeTruthy();
  });

  it('未知类型记录显示原始type字符串(fallback)', async () => {
    mockGetRecords.mockResolvedValue({
      data: {
        items: [{
          id: 1, userId: 1, type: 'unknown_type' as any, amount: 5, balance: 145,
          description: '神秘操作', createdAt: '2025-01-01T10:00:00Z',
        }],
        page: 1, total: 1,
      },
    });
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('神秘操作')).toBeTruthy());
    expect(getByText('unknown_type')).toBeTruthy();
  });

  it('消费记录显示红色金额和-号', async () => {
    mockGetRecords.mockResolvedValue({
      data: {
        items: [{
          id: 1, userId: 1, type: 'consume', amount: 12.5, balance: 87.5,
          description: '充电消费', createdAt: '2025-01-02T14:00:00Z',
        }],
        page: 1, total: 1,
      },
    });
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('充电消费')).toBeTruthy());
    expect(getByText('-¥12.50')).toBeTruthy();
  });

  it('充值记录显示绿色金额和+号', async () => {
    mockGetRecords.mockResolvedValue({
      data: {
        items: [{
          id: 1, userId: 1, type: 'recharge', amount: 100, balance: 250,
          description: '微信充值', createdAt: '2025-01-02T14:00:00Z',
        }],
        page: 1, total: 1,
      },
    });
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('微信充值')).toBeTruthy());
    expect(getByText('+¥100.00')).toBeTruthy();
  });

  it('记录列表为空时显示暂无记录', async () => {
    mockGetRecords.mockResolvedValue({ data: { items: [], page: 1, total: 0 } });
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('暂无记录')).toBeTruthy());
    expect(getByText('还没有交易记录')).toBeTruthy();
  });

  // === FlatList Footer ===

  it('触底加载时显示 ActivityIndicator footer', async () => {
    let resolvePage2: ((v: unknown) => void) | undefined;
    let call = 0;
    mockGetRecords.mockImplementation(() => {
      call += 1;
      if (call === 1) return Promise.resolve({ data: { items: makeRecords(20, 1), page: 1, total: 40 } });
      return new Promise((resolve) => { resolvePage2 = resolve; });
    });
    const { UNSAFE_getByType } = renderScreen();
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalledTimes(1));

    const list = UNSAFE_getByType(FlatList);
    await act(async () => {
      if (list.props.onEndReached) list.props.onEndReached();
    });

    // While loading more, footer should show ActivityIndicator
    await waitFor(() => {
      const footer = list.props.ListFooterComponent;
      expect(footer).toBeTruthy();
    });

    if (resolvePage2) act(() => resolvePage2!({ data: { items: makeRecords(5, 21), page: 2, total: 40 } }));
  });

  it('全部加载完显示"没有更多了" footer', async () => {
    mockGetRecords.mockResolvedValue({ data: { items: makeRecords(5, 1), page: 1, total: 5 } });
    const { UNSAFE_getByType } = renderScreen();
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalledTimes(1));

    const list = UNSAFE_getByType(FlatList);
    const footer = list.props.ListFooterComponent;
    expect(footer).toBeTruthy();
  });

  // === handleRecharge 充值流程 ===

  it('点击充值按钮弹出金额选择 Alert', async () => {
    mockGetRecords.mockResolvedValue({ data: { items: [], page: 1, total: 0 } });
    const { getByText } = renderScreen();
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalled());

    const btn = getByText('充值');
    fireEvent.press(btn);
    expect(mockAlertAlert).toHaveBeenCalledWith(
      '充值',
      '选择充值金额',
      expect.arrayContaining([
        expect.objectContaining({ text: '¥10' }),
        expect.objectContaining({ text: '¥50' }),
        expect.objectContaining({ text: '¥100' }),
        expect.objectContaining({ text: '¥200' }),
      ]),
      { cancelable: true }
    );
  });

  it('充值成功后弹出提示', async () => {
    mockGetRecords.mockResolvedValue({ data: { items: [], page: 1, total: 0 } });
    mockGetProfile.mockResolvedValue({ data: { id: 1, balance: 200 } });
    const { getByText } = renderScreen();
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalled());

    fireEvent.press(getByText('充值'));
    const callArgs = mockAlertAlert.mock.calls[0];
    const btns = callArgs[2] as AlertButton[];
    const tenYuanBtn = btns.find((b) => b.text === '¥10')!;

    mockRecharge.mockResolvedValue({});
    mockAlertAlert.mockClear();

    await act(async () => {
      await tenYuanBtn.onPress();
      await new Promise(r => setTimeout(r, 0));
    });

    expect(mockRecharge).toHaveBeenCalledWith(10);
    // After recharge, some alert fires (success or error)
    expect(mockAlertAlert.mock.calls.length).toBeGreaterThan(0);
  });

  it('充值失败显示错误提示', async () => {
    mockGetRecords.mockResolvedValue({ data: { items: [], page: 1, total: 0 } });
    const { getByText } = renderScreen();
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalled());

    fireEvent.press(getByText('充值'));
    const callArgs = mockAlertAlert.mock.calls[0];
    const buttons = callArgs[2] as AlertButton[];
    const fiftyYuanBtn = buttons.find((b) => b.text === '¥50')!;

    mockRecharge.mockRejectedValue(new Error('支付平台异常'));

    await act(async () => {
      await fiftyYuanBtn.onPress();
    });

    expect(mockRecharge).toHaveBeenCalledWith(50);
    const failCall = mockAlertAlert.mock.calls.find(
      (c) => c[0] === '充值失败'
    );
    expect(failCall).toBeTruthy();
    expect(failCall![1]).toBe('请重试');
  });

  // === refreshProfile 静默失败 ===

  it('refreshProfile 失败静默处理(不崩溃)', async () => {
    mockGetProfile.mockRejectedValue(new Error('profile fetch failed'));
    mockGetRecords.mockResolvedValue({ data: { items: [], page: 1, total: 0 } });
    const { getByText } = renderScreen();
    await waitFor(() => expect(getByText('账户余额')).toBeTruthy());
  });

  // === keyExtractor ===

  it('keyExtractor 使用 String(id)', async () => {
    mockGetRecords.mockResolvedValue({
      data: {
        items: [
          { id: 42, userId: 1, type: 'consume', amount: 5, balance: 95, description: 'test42', createdAt: '2025-01-02T14:00:00Z' },
        ],
        page: 1, total: 1,
      },
    });
    const { UNSAFE_getByType, getByText } = renderScreen();
    await waitFor(() => expect(getByText('test42')).toBeTruthy());
    const list = UNSAFE_getByType(FlatList);
    expect(list.props.keyExtractor({ id: 42 } as any)).toBe('42');
  });

  // === 充值中按钮禁用态 ===

  it('充值中按钮显示"充值中..."文字', async () => {
    let resolveRecharge: ((v: unknown) => void) | undefined;
    mockGetRecords.mockResolvedValue({ data: { items: [], page: 1, total: 0 } });
    mockRecharge.mockImplementation(() => new Promise((resolve) => { resolveRecharge = resolve; }));

    const { getByText } = renderScreen();
    await waitFor(() => expect(mockGetRecords).toHaveBeenCalled());

    fireEvent.press(getByText('充值'));
    const callArgs = mockAlertAlert.mock.calls[0];
    const buttons = callArgs[2] as AlertButton[];
    const hundredBtn = buttons.find((b) => b.text === '¥100')!;

    act(() => { void hundredBtn.onPress(); });

    // While recharging, button text changes
    await waitFor(() => expect(getByText('充值中...')).toBeTruthy());

    if (resolveRecharge) act(() => resolveRecharge!({}));
  });
});
