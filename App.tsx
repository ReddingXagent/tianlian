import React from 'react';
import { View, StyleSheet } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AppNavigator } from './src/navigation/AppNavigator';
import OfflineBanner from './src/components/OfflineBanner';

export default function App() {
  return (
    <SafeAreaProvider>
      <View style={styles.root}>
        {/* 离线感知提示条: 确认断网时顶部常驻, 在线时不渲染 */}
        <OfflineBanner />
        <AppNavigator />
      </View>
      <StatusBar style="auto" />
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});