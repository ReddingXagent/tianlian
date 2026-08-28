import React, { useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useAuthStore } from '../store/authStore';
import { useProfile } from '../hooks/useProfile';
import { useTheme } from '../hooks/useTheme';
import { RootStackParamList } from '../types';
import type { ThemeColors } from '../theme/colors';
import { formatMoney, formatEnergy } from '../utils/format';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const MENU_ITEMS = [
  { key: 'energy', label: '能源概览', icon: '📊', screen: 'Energy' as const },
  { key: 'vehicle', label: '车辆管理', icon: '🚗', screen: 'Vehicle' as const },
  { key: 'wallet', label: '我的钱包', icon: '💰', screen: 'Wallet' as const },
  { key: 'coupon', label: '我的优惠券', icon: '🎫', screen: 'Coupon' as const },
];

const ProfileScreen: React.FC = () => {
  const navigation = useNavigation<NavigationProp>();
  const { user, logout } = useAuthStore();
  const { stats } = useProfile();
  const { colors } = useTheme();

  const styles = useMemo(() => createStyles(colors), [colors]);

  const handleLogout = useCallback(() => {
    Alert.alert(
      '退出登录',
      '确定要退出当前账号吗？',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '退出',
          style: 'destructive',
          onPress: async () => {
            try {
              await logout();
            } catch {
              // 静默处理
            }
          },
        },
      ]
    );
  }, [logout]);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* 用户信息卡片 */}
      <View style={styles.profileCard}>
        <View style={styles.avatarContainer}>
          <Text style={styles.avatarText}>
            {user?.nickname?.charAt(0) || user?.phone?.charAt(0) || '?'}
          </Text>
        </View>
        <Text style={styles.nickname}>{user?.nickname || '用户'}</Text>
        <Text style={styles.phone}>{user?.phone}</Text>
        <View style={styles.balanceRow}>
          <Text style={styles.balanceLabel}>余额</Text>
          <Text style={styles.balanceValue}>¥{formatMoney(user?.balance || 0)}</Text>
        </View>
      </View>

      {/* 统计数据 */}
      <View style={styles.statsCard}>
        <View style={styles.statItem}>
          <Text style={styles.statNum}>{stats?.totalOrders || 0}</Text>
          <Text style={styles.statLabel}>总订单</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.statItem}>
          <Text style={styles.statNum}>{stats?.totalEnergy ? formatEnergy(stats.totalEnergy) : 0}</Text>
          <Text style={styles.statLabel}>充电(kWh)</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.statItem}>
          <Text style={styles.statNum}>{stats?.couponCount || 0}</Text>
          <Text style={styles.statLabel}>优惠券</Text>
        </View>
      </View>

      {/* 功能菜单 */}
      <View style={styles.menuCard}>
        {MENU_ITEMS.map((item) => (
          <TouchableOpacity accessibilityRole="button"
            key={item.key}
            style={styles.menuItem}
            onPress={() => navigation.navigate(item.screen)}
            activeOpacity={0.6}
          >
            <Text style={styles.menuIcon}>{item.icon}</Text>
            <Text style={styles.menuLabel}>{item.label}</Text>
            <Text style={styles.menuArrow}>›</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* 设置入口 */}
      <View style={styles.menuCard}>
        <TouchableOpacity style={styles.menuItem} activeOpacity={0.6}>
          <Text style={styles.menuIcon}>🔔</Text>
          <Text style={styles.menuLabel}>消息通知</Text>
          <Text style={styles.menuArrow}>›</Text>
        </TouchableOpacity>
        <View style={styles.menuDivider} />
        <TouchableOpacity style={styles.menuItem} activeOpacity={0.6}>
          <Text style={styles.menuIcon}>📖</Text>
          <Text style={styles.menuLabel}>关于我们</Text>
          <Text style={styles.menuArrow}>›</Text>
        </TouchableOpacity>
      </View>

      {/* 退出登录 */}
      <TouchableOpacity accessibilityRole="button" style={styles.logoutButton} onPress={handleLogout} activeOpacity={0.7}>
        <Text style={styles.logoutText}>退出登录</Text>
      </TouchableOpacity>

      <Text style={styles.version}>天链充电 v1.0.0</Text>
    </ScrollView>
  );
};

const createStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: colors.pageBg,
    },
    content: {
      padding: 16,
      paddingBottom: 40,
    },
    profileCard: {
      backgroundColor: colors.cardBg,
      borderRadius: 16,
      padding: 24,
      alignItems: 'center',
      marginBottom: 16,
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.08,
      shadowRadius: 8,
      elevation: 4,
    },
    avatarContainer: {
      width: 72,
      height: 72,
      borderRadius: 36,
      backgroundColor: colors.primary,
      justifyContent: 'center',
      alignItems: 'center',
      marginBottom: 12,
    },
    avatarText: {
      fontSize: 28,
      fontWeight: 'bold',
      color: colors.onPrimary,
    },
    nickname: {
      fontSize: 20,
      fontWeight: '600',
      color: colors.textPrimary,
      marginBottom: 4,
    },
    phone: {
      fontSize: 14,
      color: colors.textSecondary,
      marginBottom: 12,
    },
    balanceRow: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: colors.infoBg,
      paddingHorizontal: 16,
      paddingVertical: 8,
      borderRadius: 20,
    },
    balanceLabel: {
      fontSize: 13,
      color: colors.primary,
      marginRight: 6,
    },
    balanceValue: {
      fontSize: 16,
      fontWeight: '700',
      color: colors.primary,
    },
    statsCard: {
      flexDirection: 'row',
      backgroundColor: colors.cardBg,
      borderRadius: 12,
      padding: 16,
      marginBottom: 16,
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 1 },
      shadowOpacity: 0.05,
      shadowRadius: 4,
      elevation: 2,
    },
    statItem: {
      flex: 1,
      alignItems: 'center',
    },
    statNum: {
      fontSize: 20,
      fontWeight: '700',
      color: colors.textPrimary,
    },
    statLabel: {
      fontSize: 12,
      color: colors.textSecondary,
      marginTop: 2,
    },
    statDivider: {
      width: 1,
      backgroundColor: colors.border,
      marginHorizontal: 8,
    },
    menuCard: {
      backgroundColor: colors.cardBg,
      borderRadius: 12,
      marginBottom: 16,
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 1 },
      shadowOpacity: 0.05,
      shadowRadius: 4,
      elevation: 2,
    },
    menuItem: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: 16,
      paddingVertical: 14,
    },
    menuIcon: {
      fontSize: 18,
      marginRight: 12,
    },
    menuLabel: {
      flex: 1,
      fontSize: 15,
      color: colors.textPrimary,
    },
    menuArrow: {
      fontSize: 20,
      color: colors.textMuted,
    },
    menuDivider: {
      height: 1,
      backgroundColor: colors.divider,
      marginLeft: 50,
    },
    logoutButton: {
      backgroundColor: colors.cardBg,
      borderRadius: 12,
      paddingVertical: 14,
      alignItems: 'center',
      marginBottom: 16,
      borderWidth: 1,
      borderColor: colors.errorBg,
    },
    logoutText: {
      fontSize: 16,
      color: colors.error,
      fontWeight: '500',
    },
    version: {
      textAlign: 'center',
      fontSize: 12,
      color: colors.textMuted,
    },
  });

export default ProfileScreen;