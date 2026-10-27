import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useCallback } from 'react';
import { AppNavigator } from './src/navigation/AppNavigator';
import { useNetworkStatus } from './src/hooks/useNetworkStatus';
import { useAppState } from './src/hooks/useAppState';
import ErrorBoundary from './src/components/ErrorBoundary';
import OfflineBanner from './src/components/OfflineBanner';

export default function App() {
  useNetworkStatus();

  const handleForeground = useCallback(() => {
    // 前台恢复时各 screen 的 usePolling 自动刷新
  }, []);

  useAppState({ onForeground: handleForeground });

  return (
    <SafeAreaProvider>
      <ErrorBoundary>
        <OfflineBanner />
        <AppNavigator />
      </ErrorBoundary>
      <StatusBar style="auto" />
    </SafeAreaProvider>
  );
}
