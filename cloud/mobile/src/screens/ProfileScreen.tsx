import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
  Alert,
  Modal,
  TextInput,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useOffline } from '../store/OfflineContext';
import { authApi, profileApi } from '../services/api';
import { cache } from '../services/cache';

interface UserProfile {
  id: string;
  name: string;
  phone: string;
  email?: string;
  avatar?: string;
  stationId: string;
  stationName: string;
  role: string;
  createdAt: string;
}

interface ProfileScreenProps {
  onLogout?: () => void;
}

const ProfileScreen: React.FC<ProfileScreenProps> = ({ onLogout }) => {
  const navigation = useNavigation();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editData, setEditData] = useState({
    name: '',
    email: '',
  });
  const { isConnected, triggerSync, getCachedData } = useOffline();

  const loadData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      if (isConnected) {
        const response = await profileApi.get();
        const profileData = response.data;
        setProfile(profileData);

        // 缓存数据
        await cache.set('user_profile', profileData);
      } else {
        // 离线模式
        const cachedData = await getCachedData<UserProfile>('user_profile');
        if (cachedData) {
          setProfile(cachedData);
        }
      }
    } catch (error: any) {
      console.error('[Profile] Load error:', error.message);
      // 尝试从缓存加载
      const cachedData = await getCachedData<UserProfile>('user_profile');
      if (cachedData) {
        setProfile(cachedData);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [isConnected, getCachedData]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = async () => {
    if (isConnected) {
      await triggerSync();
      await loadData(true);
    }
  };

  const handleEditProfile = () => {
    if (profile) {
      setEditData({
        name: profile.name,
        email: profile.email || '',
      });
      setShowEditModal(true);
    }
  };

  const handleSaveProfile = async () => {
    if (!isConnected) {
      Alert.alert('提示', '离线状态下无法修改资料');
      return;
    }

    try {
      await profileApi.update({
        name: editData.name,
        email: editData.email,
      });
      Alert.alert('成功', '资料已更新');
      setShowEditModal(false);
      await loadData(true);
    } catch (error: any) {
      Alert.alert('错误', error.message || '更新失败');
    }
  };

  const handleNotifications = () => {
    navigation.navigate('Notifications' as never);
  };

  const handleLogout = async () => {
    Alert.alert(
      '退出登录',
      '确定要退出登录吗？',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '确定',
          onPress: async () => {
            try {
              if (isConnected) {
                await authApi.logout();
              }
              // 清除本地缓存
              await cache.clear();
              // 导航到登录页
              if (onLogout) {
                onLogout();
              } else {
                navigation.reset({
                  index: 0,
                  routes: [{ name: 'Login' as never }],
                });
              }
            } catch (error: any) {
              console.error('[Logout] Error:', error.message);
              // 即使 logout API 失败，也清除缓存并导航到登录页
              await cache.clear();
              if (onLogout) {
                onLogout();
              } else {
                navigation.reset({
                  index: 0,
                  routes: [{ name: 'Login' as never }],
                });
              }
            }
          },
        },
      ]
    );
  };

  if (loading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#1890ff" />
        <Text style={styles.loadingText}>加载个人资料...</Text>
      </View>
    );
  }

  if (!profile) {
    return (
      <View style={styles.centerContainer}>
        <Text style={styles.emptyIcon}>👤</Text>
        <Text style={styles.emptyText}>暂无数据</Text>
        {!isConnected && <Text style={styles.emptySubtext}>请连接网络后刷新</Text>}
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={handleRefresh}
          enabled={isConnected}
          colors={['#1890ff']}
        />
      }
    >
      {/* 个人资料头部 */}
      <View style={styles.headerSection}>
        <View style={styles.avatarContainer}>
          <View style={styles.avatarPlaceholder}>
            <Text style={styles.avatarText}>{profile.name.charAt(0)}</Text>
          </View>
          {profile.avatar && (
            <View style={styles.avatarOnlineIndicator}>
              <Text style={styles.avatarOnlineText}>在线</Text>
            </View>
          )}
        </View>
        <Text style={styles.userName}>{profile.name}</Text>
        <Text style={styles.userRole}>{profile.role}</Text>
        <Text style={styles.userStation}>{profile.stationName}</Text>
      </View>

      {/* 基本信息 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>基本信息</Text>
        <View style={styles.card}>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>姓名</Text>
            <Text style={styles.infoValue}>{profile.name}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>手机号</Text>
            <Text style={styles.infoValue}>{profile.phone}</Text>
          </View>
          {profile.email && (
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>邮箱</Text>
              <Text style={styles.infoValue}>{profile.email}</Text>
            </View>
          )}
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>所属站点</Text>
            <Text style={styles.infoValue}>{profile.stationName}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>角色</Text>
            <Text style={styles.infoValue}>{profile.role}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>入职时间</Text>
            <Text style={styles.infoValue}>{profile.createdAt}</Text>
          </View>
        </View>
      </View>

      {/* 功能入口 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>功能</Text>
        <View style={styles.card}>
          <TouchableOpacity style={styles.menuItem} onPress={handleEditProfile}>
            <View style={styles.menuLeft}>
              <Text style={styles.menuIcon}>📝</Text>
              <Text style={styles.menuText}>修改资料</Text>
            </View>
            <Text style={styles.menuArrow}>›</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.menuItem} onPress={handleNotifications}>
            <View style={styles.menuLeft}>
              <Text style={styles.menuIcon}>🔔</Text>
              <Text style={styles.menuText}>消息通知</Text>
            </View>
            <Text style={styles.menuArrow}>›</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* 系统设置 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>系统</Text>
        <View style={styles.card}>
          <TouchableOpacity style={styles.menuItem} onPress={handleLogout}>
            <View style={styles.menuLeft}>
              <Text style={[styles.menuIcon, { color: '#ff4d4f' }]}>🚪</Text>
              <Text style={[styles.menuText, { color: '#ff4d4f' }]}>退出登录</Text>
            </View>
          </TouchableOpacity>
        </View>
      </View>

      {/* 离线状态提示 */}
      {!isConnected && (
        <View style={styles.offlineNotice}>
          <Text style={styles.offlineIcon}>⚠️</Text>
          <Text style={styles.offlineText}>当前离线，部分功能受限</Text>
        </View>
      )}

      {/* 编辑资料弹窗 */}
      <Modal
        visible={showEditModal}
        transparent
        animationType="slide"
        onRequestClose={() => setShowEditModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>修改资料</Text>

            <View style={styles.modalSection}>
              <Text style={styles.modalLabel}>姓名 *</Text>
              <TextInput
                style={styles.textInput}
                placeholder="请输入姓名"
                value={editData.name}
                onChangeText={(text) => setEditData({ ...editData, name: text })}
              />
            </View>

            <View style={styles.modalSection}>
              <Text style={styles.modalLabel}>邮箱</Text>
              <TextInput
                style={styles.textInput}
                placeholder="请输入邮箱（可选）"
                value={editData.email}
                onChangeText={(text) => setEditData({ ...editData, email: text })}
                keyboardType="email-address"
              />
            </View>

            <View style={styles.modalButtons}>
              <TouchableOpacity
                style={styles.cancelButton}
                onPress={() => setShowEditModal(false)}
              >
                <Text style={styles.cancelButtonText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmButton} onPress={handleSaveProfile}>
                <Text style={styles.confirmButtonText}>保存</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  headerSection: {
    padding: 24,
    backgroundColor: '#1890ff',
    alignItems: 'center',
  },
  avatarContainer: {
    marginBottom: 16,
  },
  avatarPlaceholder: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#1890ff',
  },
  avatarOnlineIndicator: {
    position: 'absolute',
    bottom: 4,
    right: 4,
    backgroundColor: '#52c41a',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
  },
  avatarOnlineText: {
    color: '#fff',
    fontSize: 10,
  },
  userName: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 4,
  },
  userRole: {
    fontSize: 14,
    color: '#fff',
    opacity: 0.9,
    marginBottom: 4,
  },
  userStation: {
    fontSize: 14,
    color: '#fff',
    opacity: 0.7,
  },
  section: {
    padding: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#333',
    marginBottom: 12,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  infoLabel: {
    fontSize: 14,
    color: '#666',
  },
  infoValue: {
    fontSize: 14,
    color: '#333',
    fontWeight: '500',
  },
  menuItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  menuLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  menuIcon: {
    fontSize: 20,
    marginRight: 12,
  },
  menuText: {
    fontSize: 16,
    color: '#333',
  },
  menuArrow: {
    fontSize: 24,
    color: '#999',
  },
  offlineNotice: {
    backgroundColor: '#fff7e6',
    borderRadius: 8,
    padding: 16,
    margin: 16,
    flexDirection: 'row',
    alignItems: 'center',
  },
  offlineIcon: {
    fontSize: 20,
    marginRight: 12,
  },
  offlineText: {
    fontSize: 14,
    color: '#faad14',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 20,
    maxHeight: '80%',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#333',
    marginBottom: 20,
    textAlign: 'center',
  },
  modalSection: {
    marginBottom: 16,
  },
  modalLabel: {
    fontSize: 14,
    color: '#666',
    marginBottom: 8,
  },
  textInput: {
    borderWidth: 1,
    borderColor: '#d9d9d9',
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
  },
  modalButtons: {
    flexDirection: 'row',
    marginTop: 20,
  },
  cancelButton: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#d9d9d9',
    marginRight: 12,
    alignItems: 'center',
  },
  cancelButtonText: {
    fontSize: 16,
    color: '#666',
  },
  confirmButton: {
    flex: 1,
    backgroundColor: '#1890ff',
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: 'center',
  },
  confirmButtonText: {
    fontSize: 16,
    color: '#fff',
    fontWeight: '500',
  },
  loadingText: {
    marginTop: 16,
    color: '#999',
    fontSize: 14,
  },
  emptyIcon: {
    fontSize: 48,
    marginBottom: 16,
  },
  emptyText: {
    fontSize: 16,
    color: '#999',
    marginBottom: 8,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#ccc',
  },
});

export default ProfileScreen;