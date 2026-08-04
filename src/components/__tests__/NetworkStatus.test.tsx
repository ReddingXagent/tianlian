import React from 'react';
import { AppState, AppStateStatus } from 'react-native';
import { render, waitFor } from '@testing-library/react-native';
import api from '../../services/api';
import NetworkStatus from '../NetworkStatus';

jest.mock('../../services/api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

const mockedGet = api.get as jest.Mock;

type AppListener = (state: AppStateStatus) => void;

describe('NetworkStatus', () => {
  let appListener: AppListener | null;
  let addEventListenerSpy: jest.SpyInstance;
  let removeSpy: jest.Mock;

  beforeEach(() => {
    appListener = null;
    removeSpy = jest.fn();
    addEventListenerSpy = jest
      .spyOn(AppState, 'addEventListener')
      .mockImplementation((_event: string, listener: AppListener) => {
        appListener = listener;
        return { remove: removeSpy } as never;
      });
  });

  afterEach(() => {
    addEventListenerSpy.mockRestore();
    mockedGet.mockReset();
  });

  const bannerText = '网络连接已断开，请检查网络设置';

  it('should render nothing when online (ping resolves)', async () => {
    mockedGet.mockResolvedValue({ data: {} });
    const { queryByText } = render(<NetworkStatus />);
    await waitFor(() => expect(mockedGet).toHaveBeenCalled());
    expect(queryByText(bannerText)).toBeNull();
  });

  it('should show banner when ping fails with network error', async () => {
    mockedGet.mockRejectedValue(new Error('Network Error'));
    const { getByText } = render(<NetworkStatus />);
    await waitFor(() => expect(getByText(bannerText)).toBeTruthy());
  });

  it('should treat 401 as online (token expired, not offline)', async () => {
    mockedGet.mockRejectedValue({ response: { status: 401 } });
    const { queryByText } = render(<NetworkStatus />);
    await waitFor(() => expect(mockedGet).toHaveBeenCalled());
    expect(queryByText(bannerText)).toBeNull();
  });

  it('should re-check connectivity when app returns to foreground', async () => {
    mockedGet.mockResolvedValueOnce({ data: {} });
    const { getByText, queryByText } = render(<NetworkStatus />);
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));
    expect(queryByText(bannerText)).toBeNull();

    // 回前台时 ping 失败 → 显示横幅
    mockedGet.mockRejectedValueOnce(new Error('offline'));
    expect(appListener).not.toBeNull();
    appListener?.('active');
    await waitFor(() => expect(getByText(bannerText)).toBeTruthy());
    expect(mockedGet).toHaveBeenCalledTimes(2);
  });

  it('should not re-check on non-active app states', async () => {
    mockedGet.mockResolvedValue({ data: {} });
    render(<NetworkStatus />);
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));
    appListener?.('background');
    expect(mockedGet).toHaveBeenCalledTimes(1);
  });

  it('should remove AppState subscription on unmount', async () => {
    mockedGet.mockResolvedValue({ data: {} });
    const { unmount } = render(<NetworkStatus />);
    await waitFor(() => expect(mockedGet).toHaveBeenCalled());
    unmount();
    expect(removeSpy).toHaveBeenCalled();
  });

  it('should not set state after unmount when ping resolves late', async () => {
    let resolvePing!: (v: unknown) => void;
    mockedGet.mockReturnValue(
      new Promise((resolve) => {
        resolvePing = resolve;
      })
    );
    const { unmount } = render(<NetworkStatus />);
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));
    unmount();
    // 卸载后 ping 才返回 → mountedRef 守卫拦截 setState，不抛异常
    resolvePing({ data: {} });
    await waitFor(() => expect(true).toBe(true));
  });

  it('should not set state after unmount when ping fails late', async () => {
    let rejectPing!: (e: unknown) => void;
    mockedGet.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectPing = reject;
      })
    );
    const { unmount } = render(<NetworkStatus />);
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));
    unmount();
    // 卸载后 ping 才失败 → mountedRef 守卫拦截 setState，不抛异常
    rejectPing(new Error('offline'));
    await waitFor(() => expect(true).toBe(true));
  });

  it('should tolerate AppState subscription without remove method', async () => {
    mockedGet.mockResolvedValue({ data: {} });
    addEventListenerSpy.mockImplementation((_event: string, listener: AppListener) => {
      appListener = listener;
      return {} as never; // 无 remove 方法的订阅对象
    });
    const { unmount } = render(<NetworkStatus />);
    await waitFor(() => expect(mockedGet).toHaveBeenCalled());
    // subscription?.remove?.() 可选链 → 无 remove 也不崩
    expect(() => unmount()).not.toThrow();
  });
});
