import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { useAuthStore } from '../store/authStore';

const ProfileScreen: React.FC = () => {
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
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* 用户信息卡片 */}
      <View style={styles.profileCard}>
        <View style={styles.avatarContainer}>
          <Text style={styles.avatarText}>
            {user?.nickname?.charAt(0) || user?.username?.charAt(0) || '?'}
          </Text>
        </View>
        <Text style={styles.nickname}>{user?.nickname || user?.username || '未设置'}</Text>
        <View style={styles.roleBadge}>
          <Text style={styles.roleText}>{roleLabel(user?.role)}</Text>
        </View>
      </View>

      {/* 详细信息 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>账号信息</Text>
        <View style={styles.infoCard}>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>用户名</Text>
            <Text style={styles.infoValue}>{user?.username || '-'}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>昵称</Text>
            <Text style={styles.infoValue}>{user?.nickname || '-'}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>邮箱</Text>
            <Text style={styles.infoValue}>{user?.email || '-'}</Text>
          </View>
          <View style={[styles.infoRow, { borderBottomWidth: 0 }]}>
            <Text style={styles.infoLabel}>手机号</Text>
            <Text style={styles.infoValue}>{user?.phone || '-'}</Text>
          </View>
        </View>
      </View>

      {/* 设置入口 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>设置</Text>
        <View style={styles.menuCard}>
          <TouchableOpacity style={styles.menuItem} activeOpacity={0.6}>
            <Text style={styles.menuIcon}>🔔</Text>
            <Text style={styles.menuLabel}>消息通知</Text>
            <Text style={styles.menuArrow}>›</Text>
          </TouchableOpacity>
          <View style={styles.menuDivider} />
          <TouchableOpacity style={styles.menuItem} activeOpacity={0.6}>
            <Text style={styles.menuIcon}>🔒</Text>
            <Text style={styles.menuLabel}>修改密码</Text>
            <Text style={styles.menuArrow}>›</Text>
          </TouchableOpacity>
          <View style={styles.menuDivider} />
          <TouchableOpacity style={styles.menuItem} activeOpacity={0.6}>
            <Text style={styles.menuIcon}>📖</Text>
            <Text style={styles.menuLabel}>关于</Text>
            <Text style={styles.menuArrow}>›</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* 退出登录 */}
      <TouchableOpacity style={styles.logoutButton} onPress={handleLogout} activeOpacity={0.7}>
        <Text style={styles.logoutText}>退出登录</Text>
      </TouchableOpacity>

      <Text style={styles.version}>天链站长 v1.0.0</Text>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f6fa',
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  profileCard: {
    backgroundColor: '#fff',
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
    backgroundColor: '#1a73e8',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
  },
  avatarText: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#fff',
  },
  nickname: {
    fontSize: 20,
    fontWeight: '600',
    color: '#333',
    marginBottom: 6,
  },
  roleBadge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    backgroundColor: '#e3f2fd',
    borderRadius: 12,
  },
  roleText: {
    fontSize: 13,
    color: '#1a73e8',
    fontWeight: '500',
  },
  section: {
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    marginBottom: 10,
  },
  infoCard: {
    backgroundColor: '#fff',
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
    borderBottomColor: '#f0f0f0',
  },
  infoLabel: {
    fontSize: 14,
    color: '#999',
  },
  infoValue: {
    fontSize: 14,
    color: '#333',
    fontWeight: '500',
  },
  menuCard: {
    backgroundColor: '#fff',
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
    color: '#333',
  },
  menuArrow: {
    fontSize: 20,
    color: '#ccc',
  },
  menuDivider: {
    height: 1,
    backgroundColor: '#f0f0f0',
    marginLeft: 50,
  },
  logoutButton: {
    backgroundColor: '#fff',
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#fce4ec',
  },
  logoutText: {
    fontSize: 16,
    color: '#c62828',
    fontWeight: '500',
  },
  version: {
    textAlign: 'center',
    fontSize: 12,
    color: '#ccc',
  },
});

export default ProfileScreen;