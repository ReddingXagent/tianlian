import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  Alert,
  TextInput,
  Modal,
  ScrollView,
  ActivityIndicator,
} from 'react-native';
import { useRoute, RouteProp } from '@react-navigation/native';
import { useWorkOrders } from '../hooks/useWorkOrders';
import { WorkOrder, RootStackParamList, WorkOrderType, WorkOrderPriority } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';

type WorkOrderRouteProp = RouteProp<RootStackParamList, 'WorkOrder'>;

const STATUS_FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '待处理' },
  { key: 'in_progress', label: '进行中' },
  { key: 'completed', label: '已完成' },
];

const WORK_ORDER_TYPE_LABEL: Record<string, string> = {
  repair: '维修',
  inspection: '巡检',
  installation: '安装',
  maintenance: '保养',
  other: '其他',
};

const PRIORITY_CONFIG: Record<string, { label: string; color: string }> = {
  low: { label: '低', color: '#2e7d32' },
  normal: { label: '中', color: '#1565c0' },
  high: { label: '高', color: '#c62828' },
  urgent: { label: '紧急', color: '#b71c1c' },
};

const WORK_ORDER_TYPES: WorkOrderType[] = ['repair', 'inspection', 'installation', 'maintenance', 'other'];
const PRIORITIES: WorkOrderPriority[] = ['low', 'normal', 'high', 'urgent'];

const WorkOrderScreen: React.FC = () => {
  const route = useRoute<WorkOrderRouteProp>();
  const stationId = route.params?.stationId;

  const [statusFilter, setStatusFilter] = useState('all');
  const { orders, loading, refreshing, total, error, fetchData, handleLoadMore, createWorkOrder, completeWorkOrder } =
    useWorkOrders({ stationId, statusFilter });

  // Create modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createTitle, setCreateTitle] = useState('');
  const [createDesc, setCreateDesc] = useState('');
  const [createType, setCreateType] = useState<WorkOrderType>('repair');
  const [createPriority, setCreatePriority] = useState<WorkOrderPriority>('normal');
  const [creating, setCreating] = useState(false);

  const handleCreateWorkOrder = async () => {
    if (!createTitle.trim()) {
      Alert.alert('提示', '请输入工单标题');
      return;
    }
    if (!stationId) {
      Alert.alert('提示', '请先选择站点');
      return;
    }

    setCreating(true);
    const success = await createWorkOrder({
      title: createTitle.trim(),
      description: createDesc.trim(),
      type: createType,
      priority: createPriority,
    });
    setCreating(false);

    if (success) {
      Alert.alert('成功', '工单创建成功');
      setShowCreateModal(false);
      setCreateTitle('');
      setCreateDesc('');
      setCreateType('repair');
      setCreatePriority('normal');
    } else {
      Alert.alert('失败', '创建工单失败，请稍后重试');
    }
  };

  const handleCompleteOrder = (order: WorkOrder) => {
    Alert.alert(
      '完成工单',
      `确定要完成工单"${order.title}"吗？`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '确定完成',
          onPress: async () => {
            const success = await completeWorkOrder(order.id);
            if (success) {
              Alert.alert('成功', '工单已标记为完成');
            } else {
              Alert.alert('失败', '操作失败，请稍后重试');
            }
          },
        },
      ]
    );
  };

  const formatTime = (dateStr?: string): string => {
    if (!dateStr) return '-';
    const d = new Date(dateStr);
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  };

  const renderOrderItem = ({ item }: { item: WorkOrder }) => {
    const priorityConfig = PRIORITY_CONFIG[item.priority] || { label: item.priority, color: '#666' };

    return (
      <TouchableOpacity style={styles.orderCard} activeOpacity={0.7}>
        <View style={styles.orderHeader}>
          <View style={styles.orderTitleRow}>
            <Text style={styles.orderTitle} numberOfLines={1}>{item.title}</Text>
            <View style={[styles.priorityBadge, { backgroundColor: priorityConfig.color + '20' }]}>
              <Text style={[styles.priorityText, { color: priorityConfig.color }]}>
                {priorityConfig.label}
              </Text>
            </View>
          </View>
          <StatusBadge status={item.status} />
        </View>

        <Text style={styles.orderDesc} numberOfLines={2}>{item.description}</Text>

        <View style={styles.orderMeta}>
          <Text style={styles.orderMetaText}>
            {WORK_ORDER_TYPE_LABEL[item.type] || item.type}
          </Text>
          <Text style={styles.orderMetaText}>· {item.stationName}</Text>
        </View>

        <View style={styles.orderFooter}>
          <View style={styles.orderFooterLeft}>
            <Text style={styles.orderPerson}>
              {item.assigneeName ? `负责人: ${item.assigneeName}` : '未分配'}
            </Text>
            <Text style={styles.orderTime}>{formatTime(item.createdAt)}</Text>
          </View>
          {item.status === 'in_progress' && (
            <TouchableOpacity
              style={styles.completeBtn}
              onPress={() => handleCompleteOrder(item)}
             accessibilityRole="button">
              <Text style={styles.completeBtnText}>完成</Text>
            </TouchableOpacity>
          )}
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      {/* 筛选栏 */}
      <View style={styles.filterContainer}>
        <View style={styles.filterRow}>
          {STATUS_FILTERS.map((f) => (
            <TouchableOpacity
              key={f.key}
              style={[styles.filterChip, statusFilter === f.key && styles.filterChipActive]}
              onPress={() => setStatusFilter(f.key)}
             accessibilityRole="button">
              <Text style={[styles.filterChipText, statusFilter === f.key && styles.filterChipTextActive]}>
                {f.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {loading && orders.length === 0 ? (
        <LoadingSpinner text="加载工单列表..." />
      ) : error && orders.length === 0 ? (
        <EmptyState
          icon="⚠️"
          title="加载失败"
          message={error}
          actionLabel="重新加载"
          onAction={() => fetchData(false, 1)}
        />
      ) : (
        <FlatList
          data={orders}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderOrderItem}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => fetchData(true, 1)}
              colors={['#1a73e8']}
              tintColor="#1a73e8"
            />
          }
          onEndReached={handleLoadMore}
          onEndReachedThreshold={0.3}
          ListEmptyComponent={
            <EmptyState
              icon="📋"
              title="暂无工单"
              message="当前没有符合条件的工单记录"
            />
          }
          ListFooterComponent={
            orders.length > 0 && orders.length < total ? (
              <View style={styles.loadingMore}>
                <LoadingSpinner text="加载更多..." size="small" />
              </View>
            ) : orders.length >= total && total > 0 ? (
              <Text style={styles.footerText}>已显示全部 {total} 条工单</Text>
            ) : null
          }
        />
      )}

      {/* 新建工单 FAB */}
      {stationId && (
        <TouchableOpacity
          style={styles.fab}
          onPress={() => setShowCreateModal(true)}
          activeOpacity={0.8}
         accessibilityRole="button">
          <Text style={styles.fabText}>+</Text>
        </TouchableOpacity>
      )}

      {/* 新建工单弹窗 */}
      <Modal
        visible={showCreateModal}
        animationType="slide"
        transparent
        onRequestClose={() => setShowCreateModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <ScrollView>
              <Text style={styles.modalTitle}>新建工单</Text>

              <Text style={styles.modalLabel}>标题 *</Text>
              <TextInput
                style={styles.modalInput}
                placeholder="请输入工单标题"
                placeholderTextColor="#999"
                value={createTitle}
                onChangeText={setCreateTitle}
              />

              <Text style={styles.modalLabel}>描述</Text>
              <TextInput
                style={[styles.modalInput, styles.modalTextArea]}
                placeholder="请输入工单描述"
                placeholderTextColor="#999"
                value={createDesc}
                onChangeText={setCreateDesc}
                multiline
                numberOfLines={3}
              />

              <Text style={styles.modalLabel}>工单类型</Text>
              <View style={styles.pickerRow}>
                {WORK_ORDER_TYPES.map((t) => (
                  <TouchableOpacity
                    key={t}
                    style={[styles.pickerItem, createType === t && styles.pickerItemActive]}
                    onPress={() => setCreateType(t)}
                   accessibilityRole="button">
                    <Text style={[styles.pickerItemText, createType === t && styles.pickerItemTextActive]}>
                      {WORK_ORDER_TYPE_LABEL[t]}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={styles.modalLabel}>优先级</Text>
              <View style={styles.pickerRow}>
                {PRIORITIES.map((p) => {
                  const pc = PRIORITY_CONFIG[p]!;
                  return (
                    <TouchableOpacity
                      key={p}
                      style={[
                        styles.pickerItem,
                        createPriority === p && { backgroundColor: pc.color + '20', borderColor: pc.color },
                      ]}
                      onPress={() => setCreatePriority(p)}
                     accessibilityRole="button">
                      <Text style={[
                        styles.pickerItemText,
                        createPriority === p && { color: pc.color, fontWeight: '600' },
                      ]}>
                        {pc.label}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={styles.modalCancelBtn}
                  onPress={() => setShowCreateModal(false)}
                 accessibilityRole="button">
                  <Text style={styles.modalCancelText}>取消</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.modalSubmitBtn, creating && styles.modalSubmitBtnDisabled]}
                  onPress={handleCreateWorkOrder}
                  disabled={creating}
                 accessibilityRole="button">
                  {creating ? (
                    <ActivityIndicator color="#fff" size="small" />
                  ) : (
                    <Text style={styles.modalSubmitText}>创建工单</Text>
                  )}
                </TouchableOpacity>
              </View>
            </ScrollView>
          </View>
        </View>
      </Modal>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f6fa',
  },
  filterContainer: {
    backgroundColor: '#fff',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  filterRow: {
    flexDirection: 'row',
  },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: '#f5f6fa',
    marginRight: 8,
  },
  filterChipActive: {
    backgroundColor: '#1a73e8',
  },
  filterChipText: {
    fontSize: 13,
    color: '#666',
  },
  filterChipTextActive: {
    color: '#fff',
    fontWeight: '500',
  },
  listContent: {
    padding: 16,
    paddingBottom: 80,
  },
  orderCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  orderHeader: {
    marginBottom: 8,
  },
  orderTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
  },
  orderTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: '#333',
    flex: 1,
    marginRight: 8,
  },
  priorityBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
    marginRight: 8,
  },
  priorityText: {
    fontSize: 11,
    fontWeight: '500',
  },
  orderDesc: {
    fontSize: 13,
    color: '#666',
    lineHeight: 19,
    marginBottom: 8,
  },
  orderMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  orderMetaText: {
    fontSize: 12,
    color: '#999',
    marginRight: 4,
  },
  orderFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
  },
  orderFooterLeft: {},
  orderPerson: {
    fontSize: 12,
    color: '#999',
    marginBottom: 2,
  },
  orderTime: {
    fontSize: 11,
    color: '#bbb',
  },
  completeBtn: {
    backgroundColor: '#e8f5e9',
    paddingHorizontal: 16,
    paddingVertical: 6,
    borderRadius: 6,
  },
  completeBtnText: {
    fontSize: 13,
    color: '#2e7d32',
    fontWeight: '500',
  },
  loadingMore: {
    paddingVertical: 16,
  },
  footerText: {
    textAlign: 'center',
    color: '#bbb',
    fontSize: 12,
    paddingVertical: 16,
  },
  fab: {
    position: 'absolute',
    right: 20,
    bottom: 20,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#1a73e8',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#1a73e8',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 6,
  },
  fabText: {
    fontSize: 28,
    color: '#fff',
    marginTop: -2,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 24,
    maxHeight: '80%',
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: '#333',
    marginBottom: 20,
  },
  modalLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: '#333',
    marginBottom: 8,
    marginTop: 12,
  },
  modalInput: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    color: '#333',
    backgroundColor: '#fafafa',
  },
  modalTextArea: {
    minHeight: 80,
    textAlignVertical: 'top',
  },
  pickerRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  pickerItem: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#ddd',
    backgroundColor: '#fafafa',
  },
  pickerItemActive: {
    backgroundColor: '#e3f2fd',
    borderColor: '#1a73e8',
  },
  pickerItemText: {
    fontSize: 13,
    color: '#666',
  },
  pickerItemTextActive: {
    color: '#1a73e8',
    fontWeight: '600',
  },
  modalActions: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 24,
  },
  modalCancelBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#ddd',
    alignItems: 'center',
  },
  modalCancelText: {
    fontSize: 15,
    color: '#666',
    fontWeight: '500',
  },
  modalSubmitBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 8,
    backgroundColor: '#1a73e8',
    alignItems: 'center',
  },
  modalSubmitBtnDisabled: {
    opacity: 0.6,
  },
  modalSubmitText: {
    fontSize: 15,
    color: '#fff',
    fontWeight: '600',
  },
});

export default WorkOrderScreen;
