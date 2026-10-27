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
import { useTheme } from '../hooks/useTheme';
import { ThemeColors } from '../theme/colors';

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

const PRIORITY_SEMANTICS: Record<string, { label: string; color: keyof ThemeColors }> = {
  low: { label: '低', color: 'success' },
  normal: { label: '中', color: 'info' },
  high: { label: '高', color: 'error' },
  urgent: { label: '紧急', color: 'error' },
};

const WORK_ORDER_TYPES: WorkOrderType[] = ['repair', 'inspection', 'installation', 'maintenance', 'other'];
const PRIORITIES: WorkOrderPriority[] = ['low', 'normal', 'high', 'urgent'];

const WorkOrderScreen: React.FC = () => {
  const { colors } = useTheme();
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
    const prioritySemantic = PRIORITY_SEMANTICS[item.priority] || { label: item.priority, color: 'neutralText' as const };

    return (
      <TouchableOpacity style={[styles.orderCard, { backgroundColor: colors.cardBg }]} activeOpacity={0.7}>
        <View style={styles.orderHeader}>
          <View style={styles.orderTitleRow}>
            <Text style={[styles.orderTitle, { color: colors.textPrimary }]} numberOfLines={1}>{item.title}</Text>
            <View style={[styles.priorityBadge, { backgroundColor: colors[prioritySemantic.color] + '20' }]}>
              <Text style={[styles.priorityText, { color: colors[prioritySemantic.color] }]}>
                {prioritySemantic.label}
              </Text>
            </View>
          </View>
          <StatusBadge status={item.status} />
        </View>

        <Text style={[styles.orderDesc, { color: colors.textSecondary }]} numberOfLines={2}>{item.description}</Text>

        <View style={styles.orderMeta}>
          <Text style={[styles.orderMetaText, { color: colors.textSecondary }]}>
            {WORK_ORDER_TYPE_LABEL[item.type] || item.type}
          </Text>
          <Text style={[styles.orderMetaText, { color: colors.textSecondary }]}>· {item.stationName}</Text>
        </View>

        <View style={[styles.orderFooter, { borderTopColor: colors.divider }]}>
          <View style={styles.orderFooterLeft}>
            <Text style={[styles.orderPerson, { color: colors.textSecondary }]}>
              {item.assigneeName ? `负责人: ${item.assigneeName}` : '未分配'}
            </Text>
            <Text style={[styles.orderTime, { color: colors.textMuted }]}>{formatTime(item.createdAt)}</Text>
          </View>
          {item.status === 'in_progress' && (
            <TouchableOpacity
              style={[styles.completeBtn, { backgroundColor: colors.successBg }]}
              onPress={() => handleCompleteOrder(item)}
             accessibilityRole="button">
              <Text style={[styles.completeBtnText, { color: colors.success }]}>完成</Text>
            </TouchableOpacity>
          )}
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <View style={[styles.container, { backgroundColor: colors.pageBg }]}>
      {/* 筛选栏 */}
      <View style={[styles.filterContainer, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
        <View style={styles.filterRow}>
          {STATUS_FILTERS.map((f) => (
            <TouchableOpacity
              key={f.key}
              style={[styles.filterChip, { backgroundColor: colors.pageBg }, statusFilter === f.key && { backgroundColor: colors.primary }]}
              onPress={() => setStatusFilter(f.key)}
             testID={`workorder-filter-${f.key}`}
             accessibilityRole="button">
              <Text style={[styles.filterChipText, { color: colors.textSecondary }, statusFilter === f.key && { color: colors.onPrimary, fontWeight: '500' }]}>
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
              colors={[colors.primary]}
              tintColor={colors.primary}
            />
          }
          onEndReached={handleLoadMore}
          testID="workorder-list"
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
              <Text style={[styles.footerText, { color: colors.textMuted }]}>已显示全部 {total} 条工单</Text>
            ) : null
          }
        />
      )}

      {/* 新建工单 FAB */}
      {stationId && (
        <TouchableOpacity
          style={[styles.fab, { backgroundColor: colors.primary, shadowColor: colors.primary }]}
          onPress={() => setShowCreateModal(true)}
          testID="workorder-create-btn"
          activeOpacity={0.8}
         accessibilityRole="button">
          <Text style={[styles.fabText, { color: colors.onPrimary }]}>+</Text>
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
          <View style={[styles.modalContent, { backgroundColor: colors.cardBg }]}>
            <ScrollView>
              <Text style={[styles.modalTitle, { color: colors.textPrimary }]}>新建工单</Text>

              <Text style={[styles.modalLabel, { color: colors.textPrimary }]}>标题 *</Text>
              <TextInput
                style={[styles.modalInput, { borderColor: colors.border, color: colors.textPrimary, backgroundColor: colors.inputBg }]}
                placeholder="请输入工单标题"
                placeholderTextColor={colors.textSecondary}
                value={createTitle}
                testID="workorder-title-input"
                onChangeText={setCreateTitle}
              />

              <Text style={[styles.modalLabel, { color: colors.textPrimary }]}>描述</Text>
              <TextInput
                style={[styles.modalInput, styles.modalTextArea, { borderColor: colors.border, color: colors.textPrimary, backgroundColor: colors.inputBg }]}
                placeholder="请输入工单描述"
                placeholderTextColor={colors.textSecondary}
                value={createDesc}
                testID="workorder-desc-input"
                onChangeText={setCreateDesc}
                multiline
                numberOfLines={3}
              />

              <Text style={[styles.modalLabel, { color: colors.textPrimary }]}>工单类型</Text>
              <View style={styles.pickerRow}>
                {WORK_ORDER_TYPES.map((t) => (
                  <TouchableOpacity
                    key={t}
                    style={[styles.pickerItem, { borderColor: colors.border, backgroundColor: colors.inputBg }, createType === t && { backgroundColor: colors.infoBg, borderColor: colors.primary }]}
                    onPress={() => setCreateType(t)}
                   testID={`workorder-type-${t}`}
                   accessibilityRole="button">
                    <Text style={[styles.pickerItemText, { color: colors.textSecondary }, createType === t && { color: colors.primary, fontWeight: '600' }]}>
                      {WORK_ORDER_TYPE_LABEL[t]}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={[styles.modalLabel, { color: colors.textPrimary }]}>优先级</Text>
              <View style={styles.pickerRow}>
                {PRIORITIES.map((p) => {
                  const pc = PRIORITY_SEMANTICS[p]!;
                  return (
                    <TouchableOpacity
                      key={p}
                      style={[
                        styles.pickerItem,
                        { borderColor: colors.border, backgroundColor: colors.inputBg },
                        createPriority === p && { backgroundColor: colors[pc.color] + '20', borderColor: colors[pc.color] },
                      ]}
                      onPress={() => setCreatePriority(p)}
                     testID={`workorder-priority-${p}`}
                     accessibilityRole="button">
                      <Text style={[
                        styles.pickerItemText,
                        { color: colors.textSecondary },
                        createPriority === p && { color: colors[pc.color], fontWeight: '600' },
                      ]}>
                        {pc.label}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              <View style={styles.modalActions}>
                <TouchableOpacity
                  style={[styles.modalCancelBtn, { borderColor: colors.border }]}
                  onPress={() => setShowCreateModal(false)}
                 accessibilityRole="button">
                  <Text style={[styles.modalCancelText, { color: colors.textSecondary }]}>取消</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.modalSubmitBtn, { backgroundColor: colors.primary }, creating && styles.modalSubmitBtnDisabled]}
                  onPress={handleCreateWorkOrder}
                  testID="workorder-submit-btn"
                  disabled={creating}
                 accessibilityRole="button">
                  {creating ? (
                    <ActivityIndicator color={colors.onPrimary} size="small" />
                  ) : (
                    <Text style={[styles.modalSubmitText, { color: colors.onPrimary }]}>创建工单</Text>
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
  },
  filterContainer: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
  },
  filterRow: {
    flexDirection: 'row',
  },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    marginRight: 8,
  },
  filterChipText: {
    fontSize: 13,
  },
  listContent: {
    padding: 16,
    paddingBottom: 80,
  },
  orderCard: {
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
    marginRight: 4,
  },
  orderFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    borderTopWidth: 1,
  },
  orderFooterLeft: {},
  orderPerson: {
    fontSize: 12,
    marginBottom: 2,
  },
  orderTime: {
    fontSize: 11,
  },
  completeBtn: {
    paddingHorizontal: 16,
    paddingVertical: 6,
    borderRadius: 6,
  },
  completeBtnText: {
    fontSize: 13,
    fontWeight: '500',
  },
  loadingMore: {
    paddingVertical: 16,
  },
  footerText: {
    textAlign: 'center',
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
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 6,
  },
  fabText: {
    fontSize: 28,
    marginTop: -2,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 24,
    maxHeight: '80%',
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: '600',
    marginBottom: 20,
  },
  modalLabel: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 8,
    marginTop: 12,
  },
  modalInput: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
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
  },
  pickerItemText: {
    fontSize: 13,
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
    alignItems: 'center',
  },
  modalCancelText: {
    fontSize: 15,
    fontWeight: '500',
  },
  modalSubmitBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
  },
  modalSubmitBtnDisabled: {
    opacity: 0.6,
  },
  modalSubmitText: {
    fontSize: 15,
    fontWeight: '600',
  },
});

export default WorkOrderScreen;
