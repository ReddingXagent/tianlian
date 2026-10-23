import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useAuthStore } from '../store/authStore';
import { useTheme } from '../hooks/useTheme';
import type { RootStackParamList } from '../types';

type ProfileNavProp = NativeStackNavigationProp<RootStackParamList, 'Main'>;

const ProfileScreen: React.FC = () => {
  const { colors } = useTheme();
  const navigation = useNavigation<ProfileNavProp>();
  const { user, logout } = useAuthStore();

  const handleLogout = () => {
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
  };

  const roleLabel = (role?: string): string => {
    const map: Record<string, string> = {
      admin: '管理员',
      station_master: '站长',
      operator: '操作员',
      viewer: '观察者',
    };
    return role ? map[role] || role : '未知';
  };

  return (
    <ScrollView style={[styles.container, { backgroundColor: colors.pageBg }]} contentContainerStyle={styles.content}>
      {/* 用户信息卡片 */}
      <View style={[styles.profileCard, { backgroundColor: colors.cardBg }]}>
        <View style={[styles.avatarContainer, { backgroundColor: colors.primary }]}>
          <Text style={[styles.avatarText, { color: colors.onPrimary }]}>
            {user?.nickname?.charAt(0) || user?.username?.charAt(0) || '?'}
          </Text>
        </View>
        <Text style={[styles.nickname, { color: colors.textPrimary }]}>{user?.nickname || user?.username || '未设置'}</Text>
        <View style={[styles.roleBadge, { backgroundColor: colors.infoBg }]}>
          <Text style={[styles.roleText, { color: colors.info }]}>{roleLabel(user?.role)}</Text>
        </View>
      </View>

      {/* 详细信息 */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>账号信息</Text>
        <View style={[styles.infoCard, { backgroundColor: colors.cardBg }]}>
          <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>用户名</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>{user?.username || '-'}</Text>
          </View>
          <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>昵称</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>{user?.nickname || '-'}</Text>
          </View>
          <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>邮箱</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>{user?.email || '-'}</Text>
          </View>
          <View style={[styles.infoRow, { borderBottomWidth: 0 }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>手机号</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>{user?.phone || '-'}</Text>
          </View>
        </View>
      </View>

      {/* 商户服务入口 (卡 a8ca56aa 商户进件) */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>商户服务</Text>
        <View style={[styles.menuCard, { backgroundColor: colors.cardBg }]}>
          <TouchableOpacity
            style={[styles.menuItem, { borderBottomWidth: 0 }]}
            activeOpacity={0.6}
            onPress={() => navigation.navigate('MerchantKYC' as never)}
            testID="kyc-entry-btn"
            accessibilityRole="button"
          >
            <Text style={styles.menuIcon}>🏦</Text>
            <Text style={[styles.menuLabel, { color: colors.textPrimary }]}>商户进件（特约商户开通）</Text>
            <Text style={[styles.menuArrow, { color: colors.textMuted }]}>›</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* 设置入口 */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>设置</Text>
        <View style={[styles.menuCard, { backgroundColor: colors.cardBg }]}>
          <TouchableOpacity style={styles.menuItem} activeOpacity={0.6}>
            <Text style={styles.menuIcon}>🔔</Text>
            <Text style={[styles.menuLabel, { color: colors.textPrimary }]}>消息通知</Text>
            <Text style={[styles.menuArrow, { color: colors.textMuted }]}>›</Text>
          </TouchableOpacity>
          <View style={[styles.menuDivider, { backgroundColor: colors.divider }]} />
          <TouchableOpacity style={styles.menuItem} activeOpacity={0.6}>
            <Text style={styles.menuIcon}>🔒</Text>
            <Text style={[styles.menuLabel, { color: colors.textPrimary }]}>修改密码</Text>
            <Text style={[styles.menuArrow, { color: colors.textMuted }]}>›</Text>
          </TouchableOpacity>
          <View style={[styles.menuDivider, { backgroundColor: colors.divider }]} />
          <TouchableOpacity style={styles.menuItem} activeOpacity={0.6}>
            <Text style={styles.menuIcon}>📖</Text>
            <Text style={[styles.menuLabel, { color: colors.textPrimary }]}>关于</Text>
            <Text style={[styles.menuArrow, { color: colors.textMuted }]}>›</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* 退出登录 */}
      <TouchableOpacity
        style={[styles.logoutButton, { backgroundColor: colors.cardBg, borderColor: colors.errorBg }]}
        onPress={handleLogout}
        testID="profile-logout-btn"
        activeOpacity={0.7}
        accessibilityRole="button"
      >
        <Text style={[styles.logoutText, { color: colors.error }]}>退出登录</Text>
      </TouchableOpacity>

      <Text style={[styles.version, { color: colors.textMuted }]}>天链站长 v1.0.0</Text>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  profileCard: {
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
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
  },
  avatarText: {
    fontSize: 28,
    fontWeight: 'bold',
  },
  nickname: {
    fontSize: 20,
    fontWeight: '600',
    marginBottom: 6,
  },
  roleBadge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  roleText: {
    fontSize: 13,
    fontWeight: '500',
  },
  section: {
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 10,
  },
  infoCard: {
    borderRadius: 12,
    padding: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
  },
  infoLabel: {
    fontSize: 14,
  },
  infoValue: {
    fontSize: 14,
    fontWeight: '500',
  },
  menuCard: {
    borderRadius: 12,
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
  },
  menuArrow: {
    fontSize: 20,
  },
  menuDivider: {
    height: 1,
    marginLeft: 50,
  },
  logoutButton: {
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    marginBottom: 16,
    borderWidth: 1,
  },
  logoutText: {
    fontSize: 16,
    fontWeight: '500',
  },
  version: {
    textAlign: 'center',
    fontSize: 12,
  },
});

export default ProfileScreen;
