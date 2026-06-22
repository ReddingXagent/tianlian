import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { useRoute, RouteProp, useNavigation } from '@react-navigation/native';
import { useWorkOrderStore } from '../store/workOrderStore';
import { workOrderRecordApi, workOrderActionApi } from '../services/api';
import { RootStackParamList, WorkOrder, WorkOrderRecord } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';

type DetailRouteProp = RouteProp<RootStackParamList, 'WorkOrderDetail'>;

const WORK_ORDER_TYPE_LABEL: Record<string, string> = {
  repair: '维修',
  inspection: '巡检',
  installation: '安装',
  maintenance: '保养',
  other: '其他',
};

const WORK_ORDER_ACTION_LABEL: Record<string, { label: string; color: string }> = {
  created: { label: '创建工单', color: '#1a73e8' },
  accepted: { label: '接单', color: '#1565c0' },
  check_in: { label: '签到', color: '#e65100' },
  executing: { label: '开始执行', color: '#f57f17' },
  completed: { label: '完成', color: '#2e7d32' },
  cancelled: { label: '取消', color: '#616161' },
  reassigned: { label: '重新分配', color: '#6a1b9a' },
};

const WorkOrderDetailScreen: React.FC = () => {
  const route = useRoute<DetailRouteProp>();
  const navigation = useNavigation();
  const { orderId } = route.params;
  const { selectedOrder, loading, error, fetchOrderDetail, updateOrderStatus } =
    useWorkOrderStore();
  const [refreshing, setRefreshing] = useState(false);
  const [statusUpdating, setStatusUpdating] = useState(false);
  const [records, setRecords] = useState<WorkOrderRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);

  const loadData = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) setRefreshing(true);
      await Promise.all([fetchOrderDetail(orderId), loadRecords()]);
      if (isRefresh) setRefreshing(false);
    },
    [orderId, fetchOrderDetail]
  );

  const loadRecords = async () => {
    setRecordsLoading(true);
    try {
      const res = await workOrderRecordApi.getRecords(orderId);
      setRecords(res.data);
    } catch {
      // 记录加载失败不阻塞主流程
    } finally {
      setRecordsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [orderId]);

  const handleStatusChange = (newStatus: string) => {
    const labelMap: Record<string, string> = {
      pending: '待处理',
      in_progress: '进行中',
      completed: '已完成',
      cancelled: '已取消',
    };
    const statusLabel = labelMap[newStatus] || newStatus;

    Alert.alert('确认操作', `确定要将工单状态变更为"${statusLabel}"吗？`, [
      { text: '取消', style: 'cancel' },
      {
        text: '确定',
        onPress: async () => {
          setStatusUpdating(true);
          try {
            await updateOrderStatus(orderId, newStatus);
            await loadRecords();
          } catch {
            Alert.alert('操作失败', '更新工单状态失败，请重试');
          } finally {
            setStatusUpdating(false);
          }
        },
      },
    ]);
  };

  const handleAction = (action: 'accept' | 'checkIn' | 'execute' | 'complete') => {
    const confirmMessages: Record<string, string> = {
      accept: '确定要接单处理此工单吗？',
      checkIn: '确定已到达现场并签到吗？',
      execute: '确定要开始执行此工单吗？',
      complete: '确定工单已完成并提交吗？',
    };

    const actionLabels: Record<string, string> = {
      accept: '接单',
      checkIn: '签到',
      execute: '开始执行',
      complete: '完成',
    };

    Alert.alert('确认操作', confirmMessages[action], [
      { text: '取消', style: 'cancel' },
      {
        text: '确定',
        onPress: async () => {
          setStatusUpdating(true);
          try {
            if (action === 'accept') {
              await workOrderActionApi.accept(orderId);
              await updateOrderStatus(orderId, 'in_progress');
            } else if (action === 'checkIn') {
              await workOrderActionApi.checkIn(orderId);
            } else if (action === 'execute') {
              await workOrderActionApi.startExecuting(orderId);
            } else if (action === 'complete') {
              await workOrderActionApi.complete(orderId);
              await updateOrderStatus(orderId, 'completed');
            }
            await loadRecords();
            Alert.alert('操作成功', `工单已${actionLabels[action]}`);
          } catch {
            Alert.alert('操作失败', '请重试');
          } finally {
            setStatusUpdating(false);
          }
        },
      },
    ]);
  };

  if (loading && !selectedOrder) {
    return <LoadingSpinner text="加载工单详情..." />;
  }

  if (error && !selectedOrder) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error}
        actionLabel="重试"
        onAction={() => loadData()}
      />
    );
  }

  const order = selectedOrder as WorkOrder | null;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => loadData(true)}
          colors={['#1a73e8']}
          tintColor="#1a73e8"
        />
      }
    >
      {/* 工单头部 */}
      <View style={styles.headerCard}>
        <View style={styles.headerRow}>
          <Text style={styles.orderTitle}>{order?.title}</Text>
          <StatusBadge status={order?.priority ?? 'normal'} />
        </View>
        <View style={styles.headerMeta}>
          <StatusBadge status={order?.status ?? 'pending'} />
          <Text style={styles.orderType}>
            {WORK_ORDER_TYPE_LABEL[order?.type ?? 'other'] || order?.type}
          </Text>
        </View>
      </View>

      {/* 基本信息 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>基本信息</Text>
        <View style={styles.infoCard}>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>工单编号</Text>
            <Text style={styles.infoValue}>#{order?.id}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>工单类型</Text>
            <Text style={styles.infoValue}>
              {WORK_ORDER_TYPE_LABEL[order?.type ?? 'other'] || '-'}
            </Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>关联站点</Text>
            <Text style={styles.infoValue}>{order?.stationName || '-'}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>关联设备</Text>
            <Text style={styles.infoValue}>-</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>创建人</Text>
            <Text style={styles.infoValue}>{order?.creatorName || '-'}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>负责人</Text>
            <Text style={styles.infoValue}>
              {order?.assigneeName || '未分配'}
            </Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>创建时间</Text>
            <Text style={styles.infoValue}>
              {order?.createdAt
                ? new Date(order.createdAt).toLocaleString('zh-CN')
                : '-'}
            </Text>
          </View>
          <View style={[styles.infoRow, { borderBottomWidth: 0 }]}>
            <Text style={styles.infoLabel}>完成时间</Text>
            <Text style={styles.infoValue}>
              {order?.completedAt
                ? new Date(order.completedAt).toLocaleString('zh-CN')
                : '-'}
            </Text>
          </View>
        </View>
      </View>

      {/* 工单描述 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>工单描述</Text>
        <View style={styles.descCard}>
          <Text style={styles.descText}>
            {order?.description || '暂无描述'}
          </Text>
        </View>
      </View>

      {/* 操作按钮 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>操作</Text>
        <View style={styles.actionCard}>
          {order?.status === 'pending' && (
            <>
              <TouchableOpacity
                style={[styles.actionBtn, styles.actionPrimary]}
                onPress={() => handleAction('accept')}
                disabled={statusUpdating}
                activeOpacity={0.7}
              >
                {statusUpdating ? (
                  <ActivityIndicator color="#fff" size="small" />
                ) : (
                  <Text style={styles.actionBtnText}>📋 接单</Text>
                )}
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionBtn, styles.actionDanger]}
                onPress={() => handleStatusChange('cancelled')}
                disabled={statusUpdating}
                activeOpacity={0.7}
              >
                <Text style={styles.actionBtnText}>取消工单</Text>
              </TouchableOpacity>
            </>
          )}
          {order?.status === 'in_progress' && (
            <>
              <TouchableOpacity
                style={[styles.actionBtn, styles.actionWarning]}
                onPress={() => handleAction('checkIn')}
                disabled={statusUpdating}
                activeOpacity={0.7}
              >
                {statusUpdating ? (
                  <ActivityIndicator color="#fff" size="small" />
                ) : (
                  <Text style={styles.actionBtnText}>📌 签到</Text>
                )}
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionBtn, { backgroundColor: '#f57f17' }]}
                onPress={() => handleAction('execute')}
                disabled={statusUpdating}
                activeOpacity={0.7}
              >
                {statusUpdating ? (
                  <ActivityIndicator color="#fff" size="small" />
                ) : (
                  <Text style={styles.actionBtnText}>🔧 开始执行</Text>
                )}
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionBtn, styles.actionSuccess]}
                onPress={() => handleAction('complete')}
                disabled={statusUpdating}
                activeOpacity={0.7}
              >
                {statusUpdating ? (
                  <ActivityIndicator color="#fff" size="small" />
                ) : (
                  <Text style={styles.actionBtnText}>✅ 标记完成</Text>
                )}
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionBtn, styles.actionDanger]}
                onPress={() => handleStatusChange('cancelled')}
                disabled={statusUpdating}
                activeOpacity={0.7}
              >
                <Text style={styles.actionBtnText}>取消工单</Text>
              </TouchableOpacity>
            </>
          )}
          {order?.status === 'completed' && (
            <View style={styles.completedHint}>
              <Text style={styles.completedHintText}>
                ✅ 工单已完成
              </Text>
            </View>
          )}
          {order?.status === 'cancelled' && (
            <View style={styles.cancelledHint}>
              <Text style={styles.cancelledHintText}>
                ❌ 工单已取消
              </Text>
            </View>
          )}
        </View>
      </View>

      {/* 执行记录 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>执行记录</Text>
        <View style={styles.recordsCard}>
          {recordsLoading && records.length === 0 ? (
            <ActivityIndicator color="#1a73e8" style={{ padding: 20 }} />
          ) : records.length === 0 ? (
            <Text style={styles.noRecords}>暂无执行记录</Text>
          ) : (
            records.map((record, index) => {
              const actionConfig = WORK_ORDER_ACTION_LABEL[record.action] || {
                label: record.action,
                color: '#999',
              };
              return (
                <View key={record.id} style={styles.recordItem}>
                  <View style={styles.recordTimeline}>
                    <View
                      style={[
                        styles.recordDot,
                        { backgroundColor: actionConfig.color },
                      ]}
                    />
                    {index < records.length - 1 && (
                      <View style={styles.recordLine} />
                    )}
                  </View>
                  <View style={styles.recordContent}>
                    <Text style={styles.recordAction}>
                      {actionConfig.label}
                    </Text>
                    <Text style={styles.recordMeta}>
                      {record.operatorName}
                    </Text>
                    {record.note ? (
                      <Text style={styles.recordNote}>{record.note}</Text>
                    ) : null}
                    <Text style={styles.recordTime}>
                      {new Date(record.createdAt).toLocaleString('zh-CN')}
                    </Text>
                  </View>
                </View>
              );
            })
          )}
        </View>
      </View>
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
  headerCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  orderTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
    flex: 1,
    marginRight: 8,
  },
  headerMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  orderType: {
    fontSize: 13,
    color: '#999',
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
    paddingVertical: 12,
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
    textAlign: 'right',
    maxWidth: '60%',
  },
  descCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  descText: {
    fontSize: 14,
    color: '#666',
    lineHeight: 22,
  },
  actionCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
    gap: 10,
  },
  actionBtn: {
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
  },
  actionPrimary: {
    backgroundColor: '#1a73e8',
  },
  actionSuccess: {
    backgroundColor: '#2e7d32',
  },
  actionWarning: {
    backgroundColor: '#e65100',
  },
  actionDanger: {
    backgroundColor: '#c62828',
  },
  actionBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  completedHint: {
    alignItems: 'center',
    paddingVertical: 8,
  },
  completedHintText: {
    fontSize: 16,
    fontWeight: '500',
    color: '#2e7d32',
  },
  cancelledHint: {
    alignItems: 'center',
    paddingVertical: 8,
  },
  cancelledHintText: {
    fontSize: 16,
    fontWeight: '500',
    color: '#c62828',
  },
  recordsCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  noRecords: {
    textAlign: 'center',
    color: '#999',
    fontSize: 14,
    paddingVertical: 16,
  },
  recordItem: {
    flexDirection: 'row',
    marginBottom: 4,
  },
  recordTimeline: {
    width: 24,
    alignItems: 'center',
    marginRight: 12,
  },
  recordDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    marginTop: 4,
  },
  recordLine: {
    width: 2,
    flex: 1,
    backgroundColor: '#e0e0e0',
    marginVertical: 2,
  },
  recordContent: {
    flex: 1,
    paddingBottom: 16,
  },
  recordAction: {
    fontSize: 14,
    fontWeight: '500',
    color: '#333',
    marginBottom: 2,
  },
  recordMeta: {
    fontSize: 12,
    color: '#999',
    marginBottom: 2,
  },
  recordNote: {
    fontSize: 13,
    color: '#666',
    marginTop: 4,
    marginBottom: 2,
  },
  recordTime: {
    fontSize: 11,
    color: '#bbb',
    marginTop: 4,
  },
});

export default WorkOrderDetailScreen;