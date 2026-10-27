/**
 * OfflineBanner — 网络断开时顶部展示离线提示条
 * 使用 useNetworkStatus hook 感知连接状态
 * 深色模式: 语义色经 useTheme 解析
 */
import { View, Text, StyleSheet } from 'react-native';
import { useNetworkStatus } from '../hooks/useNetworkStatus';
import { useTheme } from '../hooks/useTheme';

export default function OfflineBanner() {
  const { isOffline } = useNetworkStatus();
  const { colors } = useTheme();

  if (!isOffline) return null;

  return (
    <View style={[styles.banner, { backgroundColor: colors.warning }]}>
      <Text style={[styles.text, { color: colors.onPrimary }]}>网络已断开 · 显示缓存数据</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    paddingVertical: 6,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  text: {
    fontSize: 13,
    fontWeight: '500',
  },
});
