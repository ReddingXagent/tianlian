import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  RefreshControl,
  Alert,
  Modal,
  TextInput,
} from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { RootStackParamList } from '../navigation/AppNavigator';
import { v2gApi } from '../services/api';
import type { V2GDispatch } from '../types';

type Props = NativeStackScreenProps<RootStackParamList, 'V2GDispatch'>;

type TabType = 'pending' | 'history';

const V2GDispatchScreen: React.FC<Props> = ({ navigation }) => {
  const [pendingList, setPendingList] = useState<V2GDispatch[]>([]);
  const [historyList, setHistoryList] = useState<V2GDispatch[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>('pending');
  const [rejectModal, setRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [rejectTargetId, setRejectTargetId] = useState<string | null>(null);

  const loadDispatches = useCallback(async () => {
    try {
      setLoading(true);
      const [pending, history] = await Promise.all([
        v2gApi.getPendingDispatches(),
        v2gApi.getDispatchHistory(),
      ]);
      setPendingList(pending);
      setHistoryList(history);
    } catch (error: any) {
      console.error('Load dispatches error:', error);
      setPendingList(getMockPendingDispatches());
      setHistoryList(getMockHistoryDispatches());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDispatches();
  }, [loadDispatches]);

  const getMockPendingDispatches = (): V2GDispatch[] => [
    {
      id: 'D001',
      deviceId: 'V2G001',
      deviceName: 'V2G充电桩A01',
      type: 'discharge',
      status: 'pending',
      targetPower: 30,
      targetDuration: 120,
      scheduledTime: '2026-07-07 14:00',
      createdAt: '2026-07-07 10:00',
    },
    {
      id: 'D002',
      deviceId: 'V2G002',
      deviceName: 'V2G充电桩A02',
      type: 'charge',
      status: 'pending',
      targetPower: 45,
      targetDuration: 90,
      scheduledTime: '2026-07-07 16:00',
      createdAt: '2026-07-07 11:30',
    },
    {
      id: 'D003',
      deviceId: 'V2G001',
      deviceName: 'V2G充电桩A01',
      type: 'standby',
      status: 'pending',
      targetPower: 0,
      targetDuration: 60,
      scheduledTime: '2026-07-07 18:00',
      createdAt: '2026-07-07 12:00',
    },
  ];

  const getMockHistoryDispatches = (): V2GDispatch[] => [
    {
      id: 'D100',
      deviceId: 'V2G001',
      deviceName: 'V2G充电桩A01',
      type: 'discharge',
      status: 'completed',
      targetPower: 25,
      targetDuration: 120,
      scheduledTime: '2026-07-06 14:00',
      actualPower: 24.8,
      actualDuration: 118,
      createdAt: '2026-07-06 10:00',
      completedAt: '2026-07-06 16:05',
    },
    {
      id: 'D101',
      deviceId: 'V2G002',
      deviceName: 'V2G充电桩A02',
      type: 'charge',
      status: 'rejected',
      targetPower: 50,
      targetDuration: 60,
      scheduledTime: '2026-07-06 16:00',
      rejectReason: '设备正在进行维护',
      createdAt: '2026-07-06 11:00',
    },
    {
      id: 'D102',
      deviceId: 'V2G003',
      deviceName: 'V2G充电桩B01',
      type: 'discharge',
      status: 'failed',
      targetPower: 40,
      targetDuration: 90,
      scheduledTime: '2026-07-05 14:00',
      createdAt: '2026-07-05 10:00',
      completedAt: '2026-07-05 15:00',
    },
  ];

  const getDispatchTypeInfo = (type: string) => {
    switch (type) {
      case 'charge': return { color: '#1890ff', label: '充电', icon: '⚡' };
      case 'discharge': return { color: '#faad14', label: '放电', icon: '🔋' };
      case 'standby': return { color: '#999', label: '待机', icon: '⏸️' };
      default: return { color: '#999', label: '未知', icon: '❓' };
    }
  };

  const getStatusInfo = (status: string) => {
    switch (status) {
      case 'pending': return { color: '#faad14', label: '待执行' };
      case 'confirmed': return { color: '#1890ff', label: '已确认' };
      case 'rejected': return { color: '#ff4d4f', label: '已拒绝' };
      case 'executing': return { color: '#52c41a', label: '执行中' };
      case 'completed': return { color: '#52c41a', label: '已完成' };
      case 'failed': return { color: '#ff4d4f', label: '失败' };
      default: return { color: '#999', label: '未知' };
    }
  };

  const handleConfirm = async (item: V2GDispatch) => {
    Alert.alert(
      '确认执行',
      `确定执行【${getDispatchTypeInfo(item.type).label}】调度指令？\n设备: ${item.deviceName}\n目标功率: ${item.targetPower}kW\n预计时长: ${item.targetDuration}分钟`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '确认执行',
          onPress: async () => {
            try {
              await v2gApi.confirmDispatch(item.id);
              Alert.alert('成功', '调度指令已确认执行');
              loadDispatches();
            } catch (error: any) {
              Alert.alert('失败', error.response?.data?.message || '请稍后重试');
            }
          },
        },
      ]
    );
  };

  const handleRejectPrompt = (item: V2GDispatch) => {
    setRejectTargetId(item.id);
    setRejectReason('');
    setRejectModal(true);
  };

  const handleRejectSubmit = async () => {
    if (!rejectReason.trim()) {
      Alert.alert('提示', '请填写拒绝原因');
      return;
    }
    if (!rejectTargetId) return;

    try {
      await v2gApi.rejectDispatch(rejectTargetId, rejectReason);
      Alert.alert('成功', '调度指令已拒绝');
      setRejectModal(false);
      setRejectReason('');
      setRejectTargetId(null);
      loadDispatches();
    } catch (error: any) {
      Alert.alert('失败', error.response?.data?.message || '请稍后重试');
    }
  };

  // 待执行调度卡片
  const PendingDispatchCard = ({ item }: { item: V2GDispatch }) => {
    const type = getDispatchTypeInfo(item.type);
    const status = getStatusInfo(item.status);

    return (
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <View style={[styles.typeTag, { backgroundColor: type.color }]}>
            <Text style={styles.typeTagText}>{type.icon} {type.label}</Text>
          </View>
          <View style={[styles.statusTag, { backgroundColor: status.color }]}>
            <Text style={styles.statusText}>{status.label}</Text>
          </View>
        </View>

        <View style={styles.cardBody}>
          <Text style={styles.deviceName}>{item.deviceName}</Text>
          <View style={styles.cardInfo}>
            <View style={styles.infoItem}>
              <Text style={styles.infoLabel}>目标功率</Text>
              <Text style={styles.infoValue}>{item.targetPower} kW</Text>
            </View>
            <View style={styles.infoItem}>
              <Text style={styles.infoLabel}>预计时长</Text>
              <Text style={styles.infoValue}>{item.targetDuration} 分钟</Text>
            </View>
          </View>
          <View style={styles.scheduleInfo}>
            <Text style={styles.scheduleLabel}>计划时间</Text>
            <Text style={styles.scheduleValue}>{item.scheduledTime}</Text>
          </View>
        </View>

        <View style={styles.cardActions}>
          <TouchableOpacity
            style={[styles.actionBtn, styles.confirmBtn]}
            onPress={() => handleConfirm(item)}
          >
            <Text style={styles.actionBtnText}>确认执行</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.actionBtn, styles.rejectBtn]}
            onPress={() => handleRejectPrompt(item)}
          >
            <Text style={styles.actionBtnText}>拒绝</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  // 历史调度卡片
  const HistoryDispatchCard = ({ item }: { item: V2GDispatch }) => {
    const type = getDispatchTypeInfo(item.type);
    const status = getStatusInfo(item.status);

    return (
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <View style={[styles.typeTag, { backgroundColor: type.color }]}>
            <Text style={styles.typeTagText}>{type.icon} {type.label}</Text>
          </View>
          <View style={[styles.statusTag, { backgroundColor: status.color }]}>
            <Text style={styles.statusText}>{status.label}</Text>
          </View>
        </View>

        <View style={styles.cardBody}>
          <Text style={styles.deviceName}>{item.deviceName}</Text>
          <View style={styles.cardInfo}>
            <View style={styles.infoItem}>
              <Text style={styles.infoLabel}>目标功率</Text>
              <Text style={styles.infoValue}>{item.targetPower} kW</Text>
            </View>
            <View style={styles.infoItem}>
              <Text style={styles.infoLabel}>预计时长</Text>
              <Text style={styles.infoValue}>{item.targetDuration} 分钟</Text>
            </View>
          </View>
          <View style={styles.scheduleInfo}>
            <Text style={styles.scheduleLabel}>计划时间</Text>
            <Text style={styles.scheduleValue}>{item.scheduledTime}</Text>
          </View>
          {item.status === 'completed' && item.actualPower && (
            <View style={styles.actualInfo}>
              <View style={styles.infoItem}>
                <Text style={styles.infoLabel}>实际功率</Text>
                <Text style={[styles.infoValue, styles.successText]}>{item.actualPower} kW</Text>
              </View>
              <View style={styles.infoItem}>
                <Text style={styles.infoLabel}>实际时长</Text>
                <Text style={[styles.infoValue, styles.successText]}>{item.actualDuration} 分钟</Text>
              </View>
            </View>
          )}
          {item.status === 'rejected' && item.rejectReason && (
            <View style={styles.rejectReasonBox}>
              <Text style={styles.rejectReasonLabel}>拒绝原因</Text>
              <Text style={styles.rejectReasonText}>{item.rejectReason}</Text>
            </View>
          )}
          {item.completedAt && (
            <View style={styles.completedInfo}>
              <Text style={styles.infoLabel}>完成时间</Text>
              <Text style={styles.infoValue}>{item.completedAt}</Text>
            </View>
          )}
        </View>
      </View>
    );
  };

  return (
    <View style={styles.container}>
      {/* Tab切换 */}
      <View style={styles.tabContainer}>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'pending' && styles.tabActive]}
          onPress={() => setActiveTab('pending')}
        >
          <Text style={[styles.tabText, activeTab === 'pending' && styles.tabTextActive]}>
            待执行 ({pendingList.length})
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'history' && styles.tabActive]}
          onPress={() => setActiveTab('history')}
        >
          <Text style={[styles.tabText, activeTab === 'history' && styles.tabTextActive]}>
            调度历史 ({historyList.length})
          </Text>
        </TouchableOpacity>
      </View>

      <ScrollView
        style={styles.scrollView}
        refreshControl={
          <RefreshControl refreshing={loading} onRefresh={loadDispatches} colors={['#1890ff']} />
        }
      >
        {/* 待执行列表 */}
        {activeTab === 'pending' && (
          pendingList.length > 0 ? (
            pendingList.map((item) => (
              <PendingDispatchCard key={item.id} item={item} />
            ))
          ) : (
            <View style={styles.emptyContainer}>
              <Text style={styles.emptyText}>暂无待执行调度指令</Text>
            </View>
          )
        )}

        {/* 历史列表 */}
        {activeTab === 'history' && (
          historyList.length > 0 ? (
            historyList.map((item) => (
              <HistoryDispatchCard key={item.id} item={item} />
            ))
          ) : (
            <View style={styles.emptyContainer}>
              <Text style={styles.emptyText}>暂无调度历史记录</Text>
            </View>
          )
        )}
      </ScrollView>

      {/* 拒绝原因模态框 */}
      <Modal visible={rejectModal} transparent animationType="slide">
        <View style={styles.modalContainer}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>拒绝调度指令</Text>
            <Text style={styles.modalHint}>请填写拒绝原因：</Text>
            <TextInput
              style={styles.modalInput}
              placeholder="请输入拒绝原因"
              value={rejectReason}
              onChangeText={setRejectReason}
              multiline
              numberOfLines={3}
              placeholderTextColor="#999"
            />
            <View style={styles.modalButtons}>
              <TouchableOpacity
                style={styles.modalCancelBtn}
                onPress={() => {
                  setRejectModal(false);
                  setRejectReason('');
                  setRejectTargetId(null);
                }}
              >
                <Text style={styles.modalCancelText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalSaveBtn} onPress={handleRejectSubmit}>
                <Text style={styles.modalSaveText}>提交</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  tabContainer: {
    flexDirection: 'row',
    marginHorizontal: 16,
    marginTop: 16,
    marginBottom: 12,
    backgroundColor: '#e8e8e8',
    borderRadius: 8,
    padding: 4,
  },
  tab: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderRadius: 6,
  },
  tabActive: {
    backgroundColor: '#fff',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  tabText: {
    fontSize: 14,
    color: '#666',
  },
  tabTextActive: {
    color: '#1890ff',
    fontWeight: '600',
  },
  scrollView: {
    flex: 1,
    paddingHorizontal: 16,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  typeTag: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  typeTagText: {
    fontSize: 12,
    color: '#fff',
    fontWeight: '600',
  },
  statusTag: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    fontSize: 12,
    color: '#fff',
    fontWeight: '600',
  },
  cardBody: {
    padding: 16,
  },
  deviceName: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1a1a2e',
    marginBottom: 12,
  },
  cardInfo: {
    flexDirection: 'row',
    marginBottom: 8,
  },
  infoItem: {
    flex: 1,
  },
  infoLabel: {
    fontSize: 12,
    color: '#999',
    marginBottom: 4,
  },
  infoValue: {
    fontSize: 15,
    color: '#333',
    fontWeight: '500',
  },
  scheduleInfo: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#f5f5f5',
  },
  scheduleLabel: {
    fontSize: 12,
    color: '#999',
  },
  scheduleValue: {
    fontSize: 13,
    color: '#333',
  },
  actualInfo: {
    flexDirection: 'row',
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#f5f5f5',
  },
  successText: {
    color: '#52c41a',
  },
  rejectReasonBox: {
    backgroundColor: '#fff2f0',
    borderRadius: 8,
    padding: 10,
    marginTop: 8,
  },
  rejectReasonLabel: {
    fontSize: 12,
    color: '#ff4d4f',
    marginBottom: 4,
  },
  rejectReasonText: {
    fontSize: 13,
    color: '#333',
  },
  completedInfo: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#f5f5f5',
  },
  cardActions: {
    flexDirection: 'row',
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
    gap: 8,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
  },
  confirmBtn: {
    backgroundColor: '#52c41a',
  },
  rejectBtn: {
    backgroundColor: '#ff4d4f',
  },
  actionBtnText: {
    fontSize: 14,
    color: '#fff',
    fontWeight: '600',
  },
  emptyContainer: {
    padding: 40,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 14,
    color: '#999',
  },
  // 模态框
  modalContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
  },
  modalContent: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 20,
    width: '82%',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1a1a2e',
    marginBottom: 8,
    textAlign: 'center',
  },
  modalHint: {
    fontSize: 14,
    color: '#666',
    marginBottom: 12,
  },
  modalInput: {
    borderWidth: 1,
    borderColor: '#e0e0e0',
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    marginBottom: 16,
    minHeight: 80,
    textAlignVertical: 'top',
  },
  modalButtons: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  modalCancelBtn: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#e0e0e0',
    borderRadius: 8,
    padding: 12,
    marginRight: 8,
    alignItems: 'center',
  },
  modalCancelText: {
    fontSize: 14,
    color: '#666',
  },
  modalSaveBtn: {
    flex: 1,
    backgroundColor: '#ff4d4f',
    borderRadius: 8,
    padding: 12,
    marginLeft: 8,
    alignItems: 'center',
  },
  modalSaveText: {
    fontSize: 14,
    color: '#fff',
    fontWeight: '600',
  },
});

export default V2GDispatchScreen;