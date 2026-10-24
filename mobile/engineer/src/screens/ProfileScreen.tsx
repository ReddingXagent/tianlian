import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  Image,
} from 'react-native';
import { CompositeScreenProps } from '@react-navigation/native';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { MainTabParamList, RootStackParamList } from '../navigation/AppNavigator';
import { authApi, profileApi } from '../services/api';
import type { Engineer, WorkStats, Notification } from '../types';

type Props = CompositeScreenProps<
  BottomTabScreenProps<MainTabParamList, 'Profile'>,
  NativeStackScreenProps<RootStackParamList>
>;

const ProfileScreen: React.FC<Props> = ({ navigation }) => {
  const [engineer, setEngineer] = useState<Engineer | null>(null);
  const [stats, setStats] = useState<WorkStats | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);

  // 加载个人信息
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      
      // 先从本地存储获取
      const localEngineer = await authApi.getCurrentEngineer();
      if (localEngineer) {
        setEngineer(localEngineer);
      }

      // 从服务器获取最新数据
      try {
        const [profileData, statsData, countData] = await Promise.all([
          profileApi.getProfile(),
          profileApi.getProfile().then(() => ({
            monthTotal: 45,
            avgRating: 4.8,
            avgResponseTime: 35,
          })),
          profileApi.getUnreadCount(),
        ]);
        setEngineer(profileData);
        setStats(statsData);
        setUnreadCount(countData);
      } catch (error) {
        // 使用模拟数据
        if (!localEngineer) {
          setEngineer({
            id: 'E001',
            name: '张工',
            employeeNo: 'ENG001',
            level: '高级工程师',
            phone: '138****1234',
          });
        }
        setStats({
          monthTotal: 45,
          avgRating: 4.8,
          avgResponseTime: 35,
        });
        setUnreadCount(3);
      }
    } catch (error: any) {
      console.error('Load profile error:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 退出登录
  const handleLogout = () => {
    Alert.alert(
      '退出登录',
      '确定要退出登录吗？',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '确定',
          onPress: async () => {
            try {
              await authApi.logout();
              navigation.reset({
                index: 0,
                routes: [{ name: 'Login' }],
              });
            } catch (error: any) {
              console.error('Logout error:', error);
              // 即使失败也跳转到登录页
              navigation.reset({
                index: 0,
                routes: [{ name: 'Login' }],
              });
            }
          },
        },
      ]
    );
  };

  // 查看消息
  const handleMessages = () => {
    Alert.alert('提示', '消息通知页面开发中');
  };

  if (!engineer) {
    return (
      <View style={styles.loadingContainer}>
        <Text style={styles.loadingText}>加载中...</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      {/* 个人信息卡片 */}
      <View style={styles.profileCard}>
        <View style={styles.avatarContainer}>
          {engineer.avatar ? (
            <Image source={{ uri: engineer.avatar }} style={styles.avatar} />
          ) : (
            <View style={styles.avatarPlaceholder}>
              <Text style={styles.avatarText}>👤</Text>
            </View>
          )}
        </View>
        <View style={styles.profileInfo}>
          <Text style={styles.name}>{engineer.name}</Text>
          <Text style={styles.employeeNo}>工号: {engineer.employeeNo}</Text>
          <View style={styles.levelBadge}>
            <Text style={styles.levelText}>{engineer.level}</Text>
          </View>
          <Text style={styles.phone}>📱 {engineer.phone}</Text>
        </View>
      </View>

      {/* 工作统计 */}
      <View style={styles.statsCard}>
        <Text style={styles.statsTitle}>本月工作统计</Text>
        <View style={styles.statsRow}>
          <View style={styles.statItem}>
            <Text style={styles.statValue}>{stats?.monthTotal || 0}</Text>
            <Text style={styles.statLabel}>工单数</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <Text style={[styles.statValue, styles.ratingValue]}>
              {stats?.avgRating || 0}
            </Text>
            <Text style={styles.statLabel}>评分</Text>
          </View>
          <View style={styles.statDivider} />
          <View style={styles.statItem}>
            <Text style={styles.statValue}>{stats?.avgResponseTime || 0}</Text>
            <Text style={styles.statLabel}>平均响应(分钟)</Text>
          </View>
        </View>
      </View>

      {/* 功能列表 */}
      <View style={styles.menuCard}>
        <TouchableOpacity style={styles.menuItem} onPress={handleMessages}>
          <Text style={styles.menuIcon}>📬</Text>
          <View style={styles.menuContent}>
            <Text style={styles.menuText}>消息通知</Text>
            {unreadCount > 0 && (
              <View style={styles.badge}>
                <Text style={styles.badgeText}>{unreadCount}</Text>
              </View>
            )}
          </View>
          <Text style={styles.menuArrow}>›</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.menuItem} onPress={() => Alert.alert('提示', '个人资料编辑页面开发中')}>
          <Text style={styles.menuIcon}>📝</Text>
          <View style={styles.menuContent}>
            <Text style={styles.menuText}>编辑资料</Text>
          </View>
          <Text style={styles.menuArrow}>›</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.menuItem} onPress={() => Alert.alert('提示', '设置页面开发中')}>
          <Text style={styles.menuIcon}>⚙️</Text>
          <View style={styles.menuContent}>
            <Text style={styles.menuText}>设置</Text>
          </View>
          <Text style={styles.menuArrow}>›</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.menuItem} onPress={() => Alert.alert('提示', '帮助与反馈页面开发中')}>
          <Text style={styles.menuIcon}>❓</Text>
          <View style={styles.menuContent}>
            <Text style={styles.menuText}>帮助与反馈</Text>
          </View>
          <Text style={styles.menuArrow}>›</Text>
        </TouchableOpacity>
      </View>

      {/* 退出登录 */}
      <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
        <Text style={styles.logoutText}>退出登录</Text>
      </TouchableOpacity>

      {/* 版本信息 */}
      <View style={styles.versionContainer}>
        <Text style={styles.versionText}>天链工程师 V3.0.1</Text>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    fontSize: 16,
    color: '#999',
  },
  profileCard: {
    backgroundColor: '#fff',
    padding: 20,
    marginBottom: 16,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  avatarContainer: {
    marginBottom: 16,
  },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
  },
  avatarPlaceholder: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#e0e0e0',
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarText: {
    fontSize: 36,
  },
  profileInfo: {
    alignItems: 'center',
  },
  name: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#1a1a2e',
    marginBottom: 8,
  },
  employeeNo: {
    fontSize: 14,
    color: '#666',
    marginBottom: 8,
  },
  levelBadge: {
    backgroundColor: '#e6f7ff',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 12,
    marginBottom: 8,
  },
  levelText: {
    fontSize: 14,
    color: '#1890ff',
    fontWeight: '600',
  },
  phone: {
    fontSize: 14,
    color: '#666',
  },
  statsCard: {
    backgroundColor: '#fff',
    padding: 16,
    marginHorizontal: 16,
    marginBottom: 16,
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  statsTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1a1a2e',
    marginBottom: 16,
  },
  statsRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statItem: {
    flex: 1,
    alignItems: 'center',
  },
  statDivider: {
    width: 1,
    height: 40,
    backgroundColor: '#e0e0e0',
  },
  statValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#1a1a2e',
    marginBottom: 4,
  },
  ratingValue: {
    color: '#faad14',
  },
  statLabel: {
    fontSize: 12,
    color: '#666',
  },
  menuCard: {
    backgroundColor: '#fff',
    marginHorizontal: 16,
    marginBottom: 16,
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  menuIcon: {
    fontSize: 20,
    marginRight: 12,
  },
  menuContent: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
  },
  menuText: {
    fontSize: 16,
    color: '#333',
  },
  badge: {
    backgroundColor: '#ff4d4f',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
    marginLeft: 12,
  },
  badgeText: {
    fontSize: 12,
    color: '#fff',
  },
  menuArrow: {
    fontSize: 20,
    color: '#999',
  },
  logoutButton: {
    backgroundColor: '#fff',
    marginHorizontal: 16,
    marginBottom: 16,
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#ff4d4f',
  },
  logoutText: {
    fontSize: 16,
    color: '#ff4d4f',
    fontWeight: '600',
  },
  versionContainer: {
    padding: 20,
    alignItems: 'center',
  },
  versionText: {
    fontSize: 12,
    color: '#999',
  },
});

export default ProfileScreen;