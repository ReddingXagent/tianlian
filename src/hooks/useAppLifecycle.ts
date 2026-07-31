import { useEffect, useState } from 'react';
import { AppState, AppStateStatus } from 'react-native';
import NetInfo from '@react-native-community/netinfo';

export interface AppLifecycleState {
  /** 原始 RN AppState: active | background | inactive | unknown | extension */
  appState: AppStateStatus;
  /** 是否前台 */
  isForeground: boolean;
  /** 网络是否连接; null = 尚未收到 NetInfo 首帧(视为未知, 不阻塞) */
  isConnected: boolean | null;
}

/**
 * 订阅 AppState + NetInfo, 提供前后台/网络状态。
 *
 * 移动端质量基线(F32同型缺口补齐): 此前 user-app 零 AppState/NetInfo,
 * 后台不暂停轮询(费电耗流量) + 无离线感知。本 hook 为轮询类逻辑提供
 * 统一的"该不该干活"判据。
 */
export function useAppLifecycle(): AppLifecycleState {
  const [appState, setAppState] = useState<AppStateStatus>(AppState.currentState);
  const [isConnected, setIsConnected] = useState<boolean | null>(null);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', setAppState);
    return () => subscription.remove();
  }, []);

  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener((state) => {
      setIsConnected(state.isConnected);
    });
    return () => unsubscribe();
  }, []);

  return {
    appState,
    isForeground: appState === 'active',
    isConnected,
  };
}
