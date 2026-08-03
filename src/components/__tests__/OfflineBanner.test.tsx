import React from 'react';
import { render } from '@testing-library/react-native';
import NetInfo from '@react-native-community/netinfo';
import OfflineBanner from '../OfflineBanner';

type NetInfoCb = (state: { isConnected: boolean; isInternetReachable: boolean }) => void;

describe('OfflineBanner', () => {
  const unsubscribeNetInfo = jest.fn();

  afterEach(() => {
    jest.restoreAllMocks();
    unsubscribeNetInfo.mockClear();
  });

  function mockNetInfo(firstFrame: { isConnected: boolean; isInternetReachable: boolean } | null) {
    // 每个用例开头清零: RTL自动cleanup在上一用例afterEach之后执行,
    // 其卸载触发的unsubscribe会记在共享mock上, 需先清
    unsubscribeNetInfo.mockClear();
    (NetInfo.addEventListener as jest.Mock).mockImplementation((cb: NetInfoCb) => {
      if (firstFrame) cb(firstFrame);
      return unsubscribeNetInfo;
    });
  }

  it('在线时不展示', () => {
    mockNetInfo({ isConnected: true, isInternetReachable: true });
    const { queryByTestId } = render(<OfflineBanner />);
    expect(queryByTestId('offline-banner')).toBeNull();
  });

  it('确认离线时展示提示条', () => {
    mockNetInfo({ isConnected: false, isInternetReachable: false });
    const { getByTestId, getByText } = render(<OfflineBanner />);
    expect(getByTestId('offline-banner')).toBeTruthy();
    expect(getByText('网络已断开 · 显示缓存数据')).toBeTruthy();
  });

  it('NetInfo 首帧未到(未知)时不展示, 避免启动闪条', () => {
    mockNetInfo(null);
    const { queryByTestId } = render(<OfflineBanner />);
    expect(queryByTestId('offline-banner')).toBeNull();
  });

  it('订阅在卸载时清理', () => {
    mockNetInfo({ isConnected: true, isInternetReachable: true });
    const { unmount } = render(<OfflineBanner />);
    unmount();
    expect(unsubscribeNetInfo).toHaveBeenCalledTimes(1);
  });
});
