/**
 * AppState Hook — 运维APP专用
 * 监听应用前后台切换，前台时自动刷新数据
 */
import { useEffect, useState, useCallback } from 'react';
import { AppState, AppStateStatus } from 'react-native';

interface UseAppStateOptions {
  /** 前台恢复时回调 */
  onForeground?: () => void;
  /** 进入后台时回调 */
  onBackground?: () => void;
}

export function useAppState(options: UseAppStateOptions = {}) {
  const [appState, setAppState] = useState<AppStateStatus>(AppState.currentState);
  const { onForeground, onBackground } = options;

  useEffect(() => {
    const handler = (nextState: AppStateStatus) => {
      setAppState((prev) => {
        const wasBackground = prev === 'background' || prev === 'inactive';
        const isForeground = nextState === 'active';

        if (wasBackground && isForeground) {
          onForeground?.();
        } else if (prev === 'active' && (nextState === 'background' || nextState === 'inactive')) {
          onBackground?.();
        }
        return nextState;
      });
    };

    const subscription = AppState.addEventListener('change', handler);
    return () => {
      subscription.remove();
    };
  }, [onForeground, onBackground]);

  const isForeground = useCallback(
    () => appState === 'active',
    [appState]
  );

  return {
    appState,
    isForeground,
  };
}
