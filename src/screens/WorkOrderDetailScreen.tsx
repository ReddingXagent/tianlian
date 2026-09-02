import { Alert, ScrollView, View, Text, StyleSheet, TouchableOpacity, RefreshControl, ActivityIndicator } from 'react-native';
import { WorkOrder, WorkOrderRecord } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import { useWorkOrderDetail } from '../hooks/useWorkOrderDetail';
import { useTheme } from '../hooks/useTheme';
import { ThemeColors } from '../theme/colors';

const WORK_ORDER_TYPE_LABEL: Record<string, string> = {
  repair: '维修',
  inspection: '巡检',
  installation: '安装',
  maintenance: '保养',
  other: '其他',
};

type ActionSemantic = { label: string; color: keyof ThemeColors };
const WORK_ORDER_ACTION_SEMANTICS: Record<string, ActionSemantic> = {
  created: { label: '创建工单', color: 'primary' },
  accepted: { label: '接单', color: 'info' },
  started: { label: '开始处理', color: 'warningAmber' },
  check_in: { label: '签到', color: 'warning' },
  executing: { label: '开始执行', color: 'warningAmber' },
  completed: { label: '完成', color: 'success' },
  transferred: { label: '转单', color: 'purple' },
  urged: { label: '催单', color: 'warning' },
  note: { label: '备注', color: 'neutralText' },
  cancelled: { label: '取消', color: 'neutralText' },
  reassigned: { label: '重新分配', color: 'purple' },
};

const WorkOrderDetailScreen: React.FC = () => {
  const {
    selectedOrder,
    loading,
    error,
    records,
    recordsLoading,
    refreshing,
    statusUpdating,
    loadData,
    performAction,
  } = useWorkOrderDetail();
  const { colors } = useTheme();

  const handleAction = (action: 'accept' | 'execute' | 'complete') => {
    const confirmMessages: Record<string, string> = {
      accept: '确定要接单处理此工单吗？',
      execute: '确定已到达现场并开始执行此工单吗？',
      complete: '确定工单已完成并提交吗？',
    };

    const actionLabels: Record<string, string> = {
      accept: '接单',
      execute: '开始执行',
      complete: '完成',
    };

    Alert.alert('确认操作', confirmMessages[action], [
      { text: '取消', style: 'cancel' },
      {
        text: '确定',
        onPress: async () => {
          const ok = await performAction(action);
          if (ok) {
            Alert.alert('操作成功', `工单已${actionLabels[action]}`);
          } else {
            Alert.alert('操作失败', '请重试');
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
          colors={[colors.primary]}
          tintColor={colors.primary}
        />
      }
    >
      {/* 工单头部 */}
      <View style={[styles.headerCard, { backgroundColor: colors.cardBg }]} testID="workorder-detail-card">
        <View style={styles.headerRow}>
          <Text style={[styles.orderTitle, { color: colors.textPrimary }]}>{order?.title}</Text>
          <StatusBadge status={order?.priority ?? 'normal'} />
        </View>
        <View style={styles.headerMeta}>
          <StatusBadge status={order?.status ?? 'pending'} />
          <Text style={[styles.orderType, { color: colors.textSecondary }]}>
            {WORK_ORDER_TYPE_LABEL[order?.type ?? 'other'] || order?.type}
          </Text>
        </View>
      </View>

      {/* 基本信息 */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>基本信息</Text>
        <View style={[styles.infoCard, { backgroundColor: colors.cardBg }]}>
          <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>工单编号</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>#{order?.id}</Text>
          </View>
          <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>工单类型</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>
              {WORK_ORDER_TYPE_LABEL[order?.type ?? 'other'] || '-'}
            </Text>
          </View>
          <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>关联站点</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>{order?.stationName || '-'}</Text>
          </View>
          <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>关联设备</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>-</Text>
          </View>
          <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>创建人</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>{order?.creatorName || '-'}</Text>
          </View>
          <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>负责人</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>
              {order?.assigneeName || '未分配'}
            </Text>
          </View>
          <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>创建时间</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>
              {order?.createdAt
                ? new Date(order.createdAt).toLocaleString('zh-CN')
                : '-'}
            </Text>
          </View>
          <View style={[styles.infoRow, { borderBottomWidth: 0, borderBottomColor: 'transparent' }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>完成时间</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>
              {order?.completedAt
                ? new Date(order.completedAt).toLocaleString('zh-CN')
                : '-'}
            </Text>
          </View>
        </View>
      </View>

      {/* 工单描述 */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>工单描述</Text>
        <View style={[styles.descCard, { backgroundColor: colors.cardBg }]}>
          <Text style={[styles.descText, { color: colors.textSecondary }]}>
            {order?.description || '暂无描述'}
          </Text>
        </View>
      </View>

      {/* 操作按钮 */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>操作</Text>
        <View style={[styles.actionCard, { backgroundColor: colors.cardBg }]}>
          {order?.status === 'pending' && (
            <>
              <TouchableOpacity
                style={[styles.actionBtn, { backgroundColor: colors.primary }]}
                onPress={() => handleAction('accept')}
                disabled={statusUpdating}
                activeOpacity={0.7}
               accessibilityRole="button" testID="workorder-detail-accept-btn">
                {statusUpdating ? (
                  <ActivityIndicator color={colors.onPrimary} size="small" />
                ) : (
                  <Text style={[styles.actionBtnText, { color: colors.onPrimary }]}>📋 接单</Text>
                )}
              </TouchableOpacity>
            </>
          )}
          {order?.status === 'in_progress' && (
            <>
              <TouchableOpacity
                style={[styles.actionBtn, { backgroundColor: colors.warningAmber }]}
                onPress={() => handleAction('execute')}
                disabled={statusUpdating}
                activeOpacity={0.7}
               accessibilityRole="button" testID="workorder-detail-execute-btn">
                {statusUpdating ? (
                  <ActivityIndicator color={colors.onPrimary} size="small" />
                ) : (
                  <Text style={[styles.actionBtnText, { color: colors.onPrimary }]}>🔧 到场并开始执行</Text>
                )}
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionBtn, { backgroundColor: colors.success }]}
                onPress={() => handleAction('complete')}
                disabled={statusUpdating}
                activeOpacity={0.7}
               accessibilityRole="button" testID="workorder-detail-complete-btn">
                {statusUpdating ? (
                  <ActivityIndicator color={colors.onPrimary} size="small" />
                ) : (
                  <Text style={[styles.actionBtnText, { color: colors.onPrimary }]}>✅ 标记完成</Text>
                )}
              </TouchableOpacity>
            </>
          )}
          {order?.status === 'completed' && (
            <View style={styles.completedHint}>
              <Text style={[styles.completedHintText, { color: colors.success }]}>
                ✅ 工单已完成
              </Text>
            </View>
          )}
          {order?.status === 'cancelled' && (
            <View style={styles.cancelledHint}>
              <Text style={[styles.cancelledHintText, { color: colors.error }]}>
                ❌ 工单已取消
              </Text>
            </View>
          )}
        </View>
      </View>

      {/* 执行记录 */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>执行记录</Text>
        <View style={[styles.recordsCard, { backgroundColor: colors.cardBg }]}>
          {recordsLoading && records.length === 0 ? (
            <ActivityIndicator color={colors.primary} style={{ padding: 20 }} />
          ) : records.length === 0 ? (
            <Text style={[styles.noRecords, { color: colors.textSecondary }]}>暂无执行记录</Text>
          ) : (
            records.map((record: WorkOrderRecord, index: number) => {
              const semantic = WORK_ORDER_ACTION_SEMANTICS[record.action] || {
                label: record.action,
                color: 'neutralText' as const,
              };
              return (
                <View key={record.id} style={styles.recordItem} testID={`workorder-record-${record.id}`}>
                  <View style={styles.recordTimeline}>
                    <View
                      style={[
                        styles.recordDot,
                        { backgroundColor: colors[semantic.color] },
                      ]}
                    />
                    {index < records.length - 1 && (
                      <View style={[styles.recordLine, { backgroundColor: colors.neutralBg }]} />
                    )}
                  </View>
                  <View style={styles.recordContent}>
                    <Text style={[styles.recordAction, { color: colors.textPrimary }]}>
                      {semantic.label}
                    </Text>
                    <Text style={[styles.recordMeta, { color: colors.textSecondary }]}>
                      {record.operatorName}
                    </Text>
                    {record.note ? (
                      <Text style={[styles.recordNote, { color: colors.textSecondary }]}>{record.note}</Text>
                    ) : null}
                    <Text style={[styles.recordTime, { color: colors.textMuted }]}>
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
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  headerCard: {
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
    paddingVertical: 12,
  },
  infoLabel: {
    fontSize: 14,
  },
  infoValue: {
    fontSize: 14,
    fontWeight: '500',
    textAlign: 'right',
    maxWidth: '60%',
  },
  descCard: {
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
    lineHeight: 22,
  },
  actionCard: {
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
  actionBtnText: {
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
  },
  cancelledHint: {
    alignItems: 'center',
    paddingVertical: 8,
  },
  cancelledHintText: {
    fontSize: 16,
    fontWeight: '500',
  },
  recordsCard: {
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
    marginVertical: 2,
  },
  recordContent: {
    flex: 1,
    paddingBottom: 16,
  },
  recordAction: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 2,
  },
  recordMeta: {
    fontSize: 12,
    marginBottom: 2,
  },
  recordNote: {
    fontSize: 13,
    marginTop: 4,
    marginBottom: 2,
  },
  recordTime: {
    fontSize: 11,
    marginTop: 4,
  },
});

export default WorkOrderDetailScreen;
