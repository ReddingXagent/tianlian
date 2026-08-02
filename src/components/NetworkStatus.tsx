/* eslint-disable react-hooks/set-state-in-effect */
/**
 * 网络状态横幅 — 使用 AppState 监听前后台切换
 * App 回前台时静默 ping API 检测连通性，离线时显示横幅
 * 无需额外依赖（不引入 expo-netinfo），复用现有 axios 实例
 */
import React, { useEffect, useState, useRef } from 'react';
import { View, Text, StyleSheet, AppState, AppStateStatus } from 'react-native';
import api from '../services/api';

const PING_ENDPOINT = '/auth/profile';
const PING_TIMEOUT = 5000;

export default function NetworkStatus(): React.ReactElement | null {
  const [online, setOnline] = useState(true);
  const mountedRef = useRef(true);

  const checkConnectivity = async (): Promise<void> => {
    try {
      await api.get(PING_ENDPOINT, { timeout: PING_TIMEOUT });
      if (mountedRef.current) setOnline(true);
    } catch (err: unknown) {
      // 401 = 在线但 token 过期，不算离线
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 401) {
        if (mountedRef.current) setOnline(true);
      } else if (mountedRef.current) {
        setOnline(false);
      }
    }
  };

  useEffect(() => {
    mountedRef.current = true;

    const subscription = AppState.addEventListener('change', (nextState: AppStateStatus) => {
      if (nextState === 'active') {
        checkConnectivity();
      }
    });

    // 初始检查
    checkConnectivity();

    return () => {
      mountedRef.current = false;
      subscription?.remove?.();
    };
  }, []);

  if (online) return null;

  return (
    <View style={styles.banner}>
      <Text style={styles.text}>网络连接已断开，请检查网络设置</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: '#e74c3c',
    paddingVertical: 8,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  text: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '500',
  },
});
