/**
 * OfflineBanner — 确认离线时(isConnected===false)顶部展示离线提示条。
 *
 * 移动端离线感知(F32延伸): user-app 已有 useAppLifecycle(AppState+NetInfo),
 * 但此前离线状态只用于暂停轮询, 用户无视觉反馈。本组件把离线状态呈现给用户,
 * 与 ops-app 的 OfflineBanner 对齐, 避免离线时误以为数据是实时的。
 *
 * isConnected===null(NetInfo 首帧未到)视为未知, 不展示, 避免启动闪条。
 */
import { View, Text, StyleSheet } from 'react-native';
import { useAppLifecycle } from '../hooks/useAppLifecycle';

export default function OfflineBanner() {
  const { isConnected } = useAppLifecycle();

  if (isConnected !== false) return null;

  return (
    <View style={styles.banner} testID="offline-banner">
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
