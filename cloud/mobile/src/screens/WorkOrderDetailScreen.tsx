import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
  Modal,
  TextInput,
  Alert,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useOffline } from '../store/OfflineContext';
import { workOrderApi } from '../services/api';
import { cache } from '../services/cache';

interface RouteParams {
  workOrderId: string;
}

interface WorkOrderDetail {
  id: string;
  orderNo: string;
  deviceId: string;
  deviceName: string;
  stationId: string;
  stationName: string;
  level: string;
  status: string;
  description: string;
  engineer?: {
    id: string;
    name: string;
    phone: string;
  };
  createdAt: string;
  updatedAt: string;
  completedAt?: string;
  timeline: {
    id: string;
    time: string;
    action: string;
    operator: string;
  }[];
}

const WorkOrderDetailScreen = ({ route }: { route: { params: RouteParams } }) => {
  const { workOrderId } = route.params;
  const navigation = useNavigation();
  const [workOrder, setWorkOrder] = useState<WorkOrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showAcceptModal, setShowAcceptModal] = useState(false);
  const [acceptData, setAcceptData] = useState({
    result: '',
    rating: 5,
    comment: '',
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
        const response = await workOrderApi.getById(workOrderId);
        const data = response.data;
        setWorkOrder(data);

        // 缓存数据
        await cache.set(`workorder_${workOrderId}`, data);
      } else {
        // 离线模式
        const cachedData = await getCachedData<WorkOrderDetail>(`workorder_${workOrderId}`);
        if (cachedData) {
          setWorkOrder(cachedData);
        }
      }
    } catch (error: any) {
      console.error('[WorkOrderDetail] Load error:', error.message);
      // 尝试从缓存加载
      const cachedData = await getCachedData<WorkOrderDetail>(`workorder_${workOrderId}`);
      if (cachedData) {
        setWorkOrder(cachedData);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [workOrderId, isConnected, getCachedData]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = async () => {
    if (isConnected) {
      await triggerSync();
      await loadData(true);
    }
  };

  const handleUrge = async () => {
    if (!isConnected) {
      Alert.alert('提示', '离线状态下无法催单');
      return;
    }

    try {
      await workOrderApi.urge(workOrderId);
      Alert.alert('成功', '已发送催单通知');
    } catch (error: any) {
      Alert.alert('错误', error.message || '催单失败');
    }
  };

  const handleAccept = async () => {
    if (!acceptData.result) {
      Alert.alert('提示', '请填写验收结果');
      return;
    }

    if (!isConnected) {
      Alert.alert('提示', '离线状态下无法验收');
      return;
    }

    try {
      await workOrderApi.accept(workOrderId, {
        result: acceptData.result,
        rating: acceptData.rating,
        comment: acceptData.comment,
      });

      Alert.alert('成功', '验收完成', [
        {
          text: '确定',
          onPress: () => {
            setShowAcceptModal(false);
            navigation.goBack();
          },
        },
      ]);
    } catch (error: any) {
      Alert.alert('错误', error.message || '验收失败');
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case '待处理':
        return '#ff4d4f';
      case '处理中':
        return '#faad14';
      case '已完成':
        return '#52c41a';
      case '已验收':
        return '#1890ff';
      default:
        return '#999';
    }
  };

  const getLevelColor = (level: string) => {
    switch (level) {
      case '紧急':
        return '#ff4d4f';
      case '重要':
        return '#faad14';
      case '一般':
        return '#1890ff';
      default:
        return '#999';
    }
  };

  const renderStars = (rating: number) => {
    return (
      <View style={styles.starsContainer}>
        {[1, 2, 3, 4, 5].map((star) => (
          <TouchableOpacity
            key={star}
            onPress={() => setAcceptData({ ...acceptData, rating: star })}
          >
            <Text style={[styles.star, star <= rating ? styles.starActive : null]}>
              ★
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    );
  };

  if (loading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#1890ff" />
        <Text style={styles.loadingText}>加载工单详情...</Text>
      </View>
    );
  }

  if (!workOrder) {
    return (
      <View style={styles.centerContainer}>
        <Text style={styles.emptyIcon}>📭</Text>
        <Text style={styles.emptyText}>暂无数据</Text>
        {!isConnected && <Text style={styles.emptySubtext}>请连接网络后刷新</Text>}
      </View>
    );
  }

  const canAccept = workOrder.status === '已完成';

  return (
    <View style={styles.container}>
      <ScrollView
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            enabled={isConnected}
            colors={['#1890ff']}
          />
        }
      >
        {/* 基本信息 */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>工单信息</Text>
          <View style={styles.card}>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>工单编号</Text>
              <Text style={styles.infoValue}>{workOrder.orderNo}</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>关联设备</Text>
              <Text style={styles.infoValue}>{workOrder.deviceName}</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>所属站点</Text>
              <Text style={styles.infoValue}>{workOrder.stationName}</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>工单级别</Text>
              <View style={[styles.levelBadge, { backgroundColor: getLevelColor(workOrder.level) + '20' }]}>
                <Text style={[styles.levelText, { color: getLevelColor(workOrder.level) }]}>
                  {workOrder.level}
                </Text>
              </View>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>工单状态</Text>
              <View style={[styles.statusBadge, { backgroundColor: getStatusColor(workOrder.status) + '20' }]}>
                <Text style={[styles.statusText, { color: getStatusColor(workOrder.status) }]}>
                  {workOrder.status}
                </Text>
              </View>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>创建时间</Text>
              <Text style={styles.infoValue}>{workOrder.createdAt}</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>问题描述</Text>
              <Text style={styles.infoValue}>{workOrder.description}</Text>
            </View>
          </View>
        </View>

        {/* 处理工程师 */}
        {workOrder.engineer && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>处理工程师</Text>
            <View style={styles.card}>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>工程师</Text>
                <Text style={styles.infoValue}>{workOrder.engineer.name}</Text>
              </View>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>联系电话</Text>
                <Text style={styles.infoValue}>{workOrder.engineer.phone}</Text>
              </View>
            </View>
          </View>
        )}

        {/* 处理时间线 */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>处理时间线</Text>
          {workOrder.timeline && workOrder.timeline.length > 0 ? (
            workOrder.timeline.map((item, index) => (
              <View key={item.id} style={styles.timelineItem}>
                <View style={styles.timelineLeft}>
                  <View style={[styles.timelineDot, index === 0 ? styles.timelineDotActive : null]} />
                  {index < workOrder.timeline.length - 1 && <View style={styles.timelineLine} />}
                </View>
                <View style={styles.timelineContent}>
                  <Text style={styles.timelineTime}>{item.time}</Text>
                  <Text style={styles.timelineAction}>{item.action}</Text>
                  <Text style={styles.timelineOperator}>操作人: {item.operator}</Text>
                </View>
              </View>
            ))
          ) : (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyText}>暂无处理记录</Text>
            </View>
          )}
        </View>
      </ScrollView>

      {/* 底部操作 */}
      <View style={styles.bottomBar}>
        {canAccept && (
          <TouchableOpacity
            style={styles.acceptButton}
            onPress={() => setShowAcceptModal(true)}
          >
            <Text style={styles.acceptButtonText}>确认验收</Text>
          </TouchableOpacity>
        )}
        {workOrder.status === '处理中' && (
          <TouchableOpacity style={styles.urgeButton} onPress={handleUrge}>
            <Text style={styles.urgeButtonText}>催单</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* 验收弹窗 */}
      <Modal
        visible={showAcceptModal}
        transparent
        animationType="slide"
        onRequestClose={() => setShowAcceptModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>确认验收</Text>

            <View style={styles.modalSection}>
              <Text style={styles.modalLabel}>验收结果 *</Text>
              <TextInput
                style={styles.textInput}
                placeholder="请描述验收结果"
                value={acceptData.result}
                onChangeText={(text) => setAcceptData({ ...acceptData, result: text })}
                multiline
                numberOfLines={3}
              />
            </View>

            <View style={styles.modalSection}>
              <Text style={styles.modalLabel}>服务评价</Text>
              {renderStars(acceptData.rating)}
            </View>

            <View style={styles.modalSection}>
              <Text style={styles.modalLabel}>评价说明</Text>
              <TextInput
                style={styles.textInput}
                placeholder="请填写评价说明（可选）"
                value={acceptData.comment}
                onChangeText={(text) => setAcceptData({ ...acceptData, comment: text })}
                multiline
                numberOfLines={2}
              />
            </View>

            <View style={styles.modalButtons}>
              <TouchableOpacity
                style={styles.cancelButton}
                onPress={() => setShowAcceptModal(false)}
              >
                <Text style={styles.cancelButtonText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmButton} onPress={handleAccept}>
                <Text style={styles.confirmButtonText}>确认</Text>
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
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
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
    flex: 1,
    textAlign: 'right',
  },
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    fontSize: 14,
    fontWeight: '500',
  },
  levelBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 10,
  },
  levelText: {
    fontSize: 14,
    fontWeight: '500',
  },
  timelineItem: {
    flexDirection: 'row',
    marginBottom: 16,
  },
  timelineLeft: {
    width: 24,
    alignItems: 'center',
  },
  timelineDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: '#d9d9d9',
  },
  timelineDotActive: {
    backgroundColor: '#1890ff',
  },
  timelineLine: {
    width: 2,
    flex: 1,
    backgroundColor: '#e8e8e8',
    marginTop: 4,
  },
  timelineContent: {
    flex: 1,
    marginLeft: 12,
    backgroundColor: '#fff',
    borderRadius: 8,
    padding: 12,
  },
  timelineTime: {
    fontSize: 12,
    color: '#999',
    marginBottom: 4,
  },
  timelineAction: {
    fontSize: 14,
    color: '#333',
    fontWeight: '500',
    marginBottom: 4,
  },
  timelineOperator: {
    fontSize: 12,
    color: '#666',
  },
  emptyCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
  },
  bottomBar: {
    padding: 16,
    backgroundColor: '#fff',
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
  },
  acceptButton: {
    backgroundColor: '#52c41a',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
  },
  acceptButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '500',
  },
  urgeButton: {
    backgroundColor: '#faad14',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
  },
  urgeButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '500',
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
    textAlignVertical: 'top',
  },
  starsContainer: {
    flexDirection: 'row',
  },
  star: {
    fontSize: 32,
    color: '#d9d9d9',
    marginRight: 8,
  },
  starActive: {
    color: '#faad14',
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

export default WorkOrderDetailScreen;