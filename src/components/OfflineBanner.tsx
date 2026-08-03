/**
 * OfflineBanner — 网络断开时顶部展示离线提示条
 * 使用 useNetworkStatus hook 感知连接状态
 */
import { View, Text, StyleSheet } from 'react-native';
import { useNetworkStatus } from '../hooks/useNetworkStatus';

export default function OfflineBanner() {
  const { isOffline } = useNetworkStatus();

  if (!isOffline) return null;

  return (
    <View style={styles.banner}>
      <Text style={styles.text}>网络已断开 · 显示缓存数据</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: '#e65100',
    paddingVertical: 6,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  text: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '500',
  },
});
