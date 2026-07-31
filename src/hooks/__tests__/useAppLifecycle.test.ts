import { renderHook, act } from '@testing-library/react-native';
import { AppState } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { useAppLifecycle } from '../useAppLifecycle';

type NetInfoCb = (state: { isConnected: boolean; isInternetReachable: boolean }) => void;

describe('useAppLifecycle', () => {
  let appStateCb: ((state: string) => void) | null = null;
  let netInfoCb: NetInfoCb | null = null;
  const removeAppState = jest.fn();
  const unsubscribeNetInfo = jest.fn();

  beforeEach(() => {
    appStateCb = null;
    netInfoCb = null;
    removeAppState.mockClear();
    unsubscribeNetInfo.mockClear();
    jest.spyOn(AppState, 'addEventListener').mockImplementation(((_e: string, cb: unknown) => {
      appStateCb = cb as (state: string) => void;
      return { remove: removeAppState };
    }) as typeof AppState.addEventListener);
    (NetInfo.addEventListener as jest.Mock).mockImplementation((cb: NetInfoCb) => {
      netInfoCb = cb;
      return unsubscribeNetInfo;
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('初始: 前台, 连接状态未知(NetInfo首帧未到不阻塞)', () => {
    const { result } = renderHook(() => useAppLifecycle());
    expect(result.current.appState).toBe('active');
    expect(result.current.isForeground).toBe(true);
    expect(result.current.isConnected).toBeNull();
  });

  it('NetInfo回调更新 isConnected', () => {
    const { result } = renderHook(() => useAppLifecycle());
    act(() => netInfoCb?.({ isConnected: false, isInternetReachable: false }));
    expect(result.current.isConnected).toBe(false);
    act(() => netInfoCb?.({ isConnected: true, isInternetReachable: true }));
    expect(result.current.isConnected).toBe(true);
  });

  it('AppState变化更新 isForeground', () => {
    const { result } = renderHook(() => useAppLifecycle());
    act(() => appStateCb?.('background'));
    expect(result.current.appState).toBe('background');
    expect(result.current.isForeground).toBe(false);
    act(() => appStateCb?.('active'));
    expect(result.current.isForeground).toBe(true);
  });

  it('卸载时清理两个订阅', () => {
    const { unmount } = renderHook(() => useAppLifecycle());
    unmount();
    expect(removeAppState).toHaveBeenCalledTimes(1);
    expect(unsubscribeNetInfo).toHaveBeenCalledTimes(1);
  });
});
