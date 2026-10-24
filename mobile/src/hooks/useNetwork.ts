import { useState, useEffect } from 'react';
import NetInfo from '@react-native-community/netinfo';
import type { NetInfoState } from '@react-native-community/netinfo';

export interface NetworkState {
  isConnected: boolean;
  isInternetReachable: boolean | null;
  type: string | null;
}

/**
 * 网络状态 Hook
 * 实时监测设备网络连接状态
 */
export const useNetwork = () => {
  const [networkState, setNetworkState] = useState<NetworkState>({
    isConnected: false,
    isInternetReachable: null,
    type: null,
  });

  useEffect(() => {
    // 订阅网络状态变化
    const unsubscribe = NetInfo.addEventListener((state: NetInfoState) => {
      console.log('[Network] State changed:', state);
      setNetworkState({
        isConnected: state.isConnected ?? false,
        isInternetReachable: state.isInternetReachable,
        type: state.type ?? null,
      });
    });

    // 初始检查
    NetInfo.fetch().then((state: NetInfoState) => {
      console.log('[Network] Initial state:', state);
      setNetworkState({
        isConnected: state.isConnected ?? false,
        isInternetReachable: state.isInternetReachable,
        type: state.type ?? null,
      });
    });

    return () => {
      unsubscribe();
    };
  }, []);

  return networkState;
};

/**
 * 简化版 Hook - 只返回是否在线
 */
export const useIsOnline = (): boolean => {
  const { isConnected } = useNetwork();
  return isConnected;
};
