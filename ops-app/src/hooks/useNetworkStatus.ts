/**
 * 网络状态 Hook — 运维APP专用
 * 监听网络连接状态，支持离线感知和数据刷新联动
 */
import { useEffect, useState, useCallback } from 'react';
import { Platform } from 'react-native';

interface NetworkState {
  isConnected: boolean;
  isInternetReachable: boolean | null;
  type: string;
}

function getWebNetworkState(): NetworkState {
  return {
    isConnected: navigator.onLine,
    isInternetReachable: navigator.onLine,
    type: navigator.onLine ? 'wifi' : 'none',
  };
}

interface NetInfoState {
  isConnected: boolean | null;
  isInternetReachable: boolean | null;
  type: string;
}

interface NetInfoModule {
  fetch: () => Promise<NetInfoState>;
  addEventListener: (cb: (state: NetInfoState) => void) => () => void;
}

// Static require for testability — dynamic import() is not mockable in Jest
// without --experimental-vm-modules. In production, RN bundler resolves this.
let cachedNetInfo: NetInfoModule | null | undefined;
function loadNetInfo(): NetInfoModule | null {
  if (cachedNetInfo !== undefined) return cachedNetInfo;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mod: unknown = require('@react-native-community/netinfo');
    cachedNetInfo = ((mod as { default?: NetInfoModule }).default ??
      (mod as NetInfoModule)) as NetInfoModule;
    return cachedNetInfo;
  } catch {
    cachedNetInfo = null;
    return null;
  }
}

export function useNetworkStatus() {
  const [networkState, setNetworkState] = useState<NetworkState>({
    isConnected: true,
    isInternetReachable: true,
    type: 'unknown',
  });

  useEffect(() => {
    let mounted = true;
    let unsubscribe: (() => void) | null = null;

    if (Platform.OS === 'web') {
      const handler = () => {
        if (mounted) setNetworkState(getWebNetworkState());
      };
      // 初始读取 + 监听变化
      const initial = getWebNetworkState();
      window.addEventListener('online', handler);
      window.addEventListener('offline', handler);
      // 使用微任务避免 render 阶段 setState
      Promise.resolve().then(() => {
        if (mounted) setNetworkState(initial);
      });
      return () => {
        mounted = false;
        window.removeEventListener('online', handler);
        window.removeEventListener('offline', handler);
      };
    }

    const setup = async () => {
      const NetInfo = loadNetInfo();
      if (!mounted || !NetInfo) return;

      const state = await NetInfo.fetch();
      if (!mounted) return;
      setNetworkState({
        isConnected: state.isConnected ?? false,
        isInternetReachable: state.isInternetReachable,
        type: state.type,
      });

      unsubscribe = NetInfo.addEventListener((s: NetInfoState) => {
        if (!mounted) return;
        setNetworkState({
          isConnected: s.isConnected ?? false,
          isInternetReachable: s.isInternetReachable,
          type: s.type,
        });
      });
    };

    setup();

    return () => {
      mounted = false;
      unsubscribe?.();
    };
  }, []);

  const refresh = useCallback(async () => {
    if (Platform.OS === 'web') {
      setNetworkState(getWebNetworkState());
      return;
    }
    const NetInfo = loadNetInfo();
    if (!NetInfo) return;
    const state = await NetInfo.fetch();
    setNetworkState({
      isConnected: state.isConnected ?? false,
      isInternetReachable: state.isInternetReachable,
      type: state.type,
    });
  }, []);

  return {
    ...networkState,
    isOffline: !networkState.isConnected,
    refresh,
  };
}
