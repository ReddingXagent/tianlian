import { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  Alert,
  ActivityIndicator,
  TextInput,
} from 'react-native';
import { useInspectionDetail } from '../hooks/useInspectionDetail';
import { InspectionTask, InspectionItem } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import { useTheme } from '../hooks/useTheme';

const TYPE_LABELS: Record<string, string> = {
  daily: '日检', weekly: '周检', monthly: '月检', quarterly: '季检', annual: '年检', special: '特检',
};

const getResultIcon = (result?: string) => {
  switch (result) {
    case 'pass': return '✅';
    case 'fail': return '❌';
    case 'na': return '➖';
    default: return '⬜';
  }
};

const InspectionDetailScreen: React.FC = () => {
  const {
    selectedTask,
    loading,
    error,
    submitting,
    refreshing,
    loadData,
    handleStart,
    handleItemResult,
    handleComplete,
  } = useInspectionDetail();
  const { colors } = useTheme();

  const [completionNote, setCompletionNote] = useState('');
  const [showCompleteForm, setShowCompleteForm] = useState(false);

  const onStart = () => {
    Alert.alert('开始巡检', '确定要开始执行此巡检任务吗？', [
      { text: '取消', style: 'cancel' },
      { text: '确定', onPress: () => handleStart() },
    ]);
  };

  const onComplete = async () => {
    if (!completionNote.trim()) {
      Alert.alert('提示', '请填写巡检总结');
      return;
    }
    await handleComplete(completionNote.trim());
    setShowCompleteForm(false);
    setCompletionNote('');
  };

  if (loading && !selectedTask) {
    return <LoadingSpinner text="加载巡检详情..." />;
  }

  if (error && !selectedTask) {
    return <EmptyState icon="⚠️" title="加载失败" message={error} actionLabel="重试" onAction={() => loadData()} />;
  }

  const task = selectedTask as InspectionTask | null;

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.pageBg }]}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => loadData(true)} colors={[colors.primary]} tintColor={colors.primary} />
      }
    >
      {/* Header */}
      <View style={[styles.headerCard, { backgroundColor: colors.cardBg }]}>
        <View style={styles.headerRow}>
          <Text style={[styles.taskTitle, { color: colors.textPrimary }]} numberOfLines={2}>{task?.description}</Text>
          <StatusBadge status={task?.status ?? 'pending'} />
        </View>
        <View style={styles.headerMeta}>
          <View style={[styles.typeBadge, { backgroundColor: colors.infoBg }]}>
            <Text style={[styles.typeText, { color: colors.info }]}>{TYPE_LABELS[task?.type ?? 'daily'] || task?.type}</Text>
          </View>
          <Text style={[styles.headerStation, { color: colors.textSecondary }]}>{task?.stationName}</Text>
        </View>
      </View>

      {/* Info */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>基本信息</Text>
        <View style={[styles.infoCard, { backgroundColor: colors.cardBg }]}>
          <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>设备名称</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>{task?.deviceName || '-'}</Text>
          </View>
          <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>计划日期</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>{task?.scheduledDate ? new Date(task.scheduledDate).toLocaleDateString('zh-CN') : '-'}</Text>
          </View>
          <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>负责人</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>{task?.assignedName || '未分配'}</Text>
          </View>
          <View style={[styles.infoRow, { borderBottomWidth: 0 }]}>
            <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>完成日期</Text>
            <Text style={[styles.infoValue, { color: colors.textPrimary }]}>{task?.completedDate ? new Date(task.completedDate).toLocaleDateString('zh-CN') : '-'}</Text>
          </View>
        </View>
      </View>

      {/* Inspection Items */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>检查项目 ({task?.items?.length || 0})</Text>
        {task?.items?.map((item: InspectionItem) => (
          <View key={item.id} style={[styles.itemCard, { backgroundColor: colors.cardBg }]}>
            <View style={styles.itemHeader}>
              <Text style={[styles.itemName, { color: colors.textPrimary }]} numberOfLines={2}>{item.name}</Text>
              <Text style={styles.itemResultIcon}>{getResultIcon(item.result)}</Text>
            </View>
            <Text style={[styles.itemExpected, { color: colors.textSecondary }]}>标准: {item.expected}</Text>
            {item.note && <Text style={[styles.itemNote, { color: colors.textSecondary }]}>备注: {item.note}</Text>}

            {task.status === 'in_progress' && !item.result && (
              <View style={styles.itemActions}>
                <TouchableOpacity style={[styles.passBtn, { backgroundColor: colors.successBg }]} onPress={() => handleItemResult(item, 'pass')} disabled={submitting} accessibilityRole="button">
                  <Text style={[styles.actionBtnText, { color: colors.textPrimary }]}>✅ 通过</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.failBtn, { backgroundColor: colors.errorBg }]} onPress={() => handleItemResult(item, 'fail')} disabled={submitting} accessibilityRole="button">
                  <Text style={[styles.actionBtnText, { color: colors.textPrimary }]}>❌ 不通过</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.naBtn, { backgroundColor: colors.neutralBg }]} onPress={() => handleItemResult(item, 'na')} disabled={submitting} accessibilityRole="button">
                  <Text style={[styles.actionBtnText, { color: colors.textPrimary }]}>N/A</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        ))}
      </View>

      {/* Result summary */}
      {task?.result && (
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>巡检结果</Text>
          <View style={[styles.resultCard, { backgroundColor: colors.cardBg }]}>
            <View style={styles.resultHeader}>
              <Text style={[styles.resultOverall, { color: colors.textPrimary }]}>
                {task.result.overall === 'pass' ? '✅ 通过' : task.result.overall === 'partial' ? '⚠️ 部分通过' : '❌ 未通过'}
              </Text>
            </View>
            <Text style={[styles.resultSummary, { color: colors.textSecondary }]}>{task.result.summary}</Text>
            <View style={[styles.resultMeta, { borderTopColor: colors.divider }]}>
              <Text style={[styles.resultMetaText, { color: colors.textSecondary }]}>操作人: {task.result.operatorName}</Text>
              <Text style={[styles.resultMetaText, { color: colors.textSecondary }]}>{new Date(task.result.completedAt).toLocaleString('zh-CN')}</Text>
            </View>
          </View>
        </View>
      )}

      {/* Actions */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>操作</Text>
        <View style={[styles.actionCard, { backgroundColor: colors.cardBg }]}>
          {task?.status === 'pending' && (
            <TouchableOpacity style={[styles.actionBtn, styles.actionPrimary, { backgroundColor: colors.primary }]} onPress={onStart} disabled={submitting} activeOpacity={0.7} accessibilityRole="button">
              {submitting ? <ActivityIndicator color={colors.onPrimary} size="small" /> : <Text style={[styles.actionBtnText, { color: colors.onPrimary }]}>开始巡检</Text>}
            </TouchableOpacity>
          )}

          {task?.status === 'in_progress' && (
            <>
              {!showCompleteForm ? (
                <TouchableOpacity style={[styles.actionBtn, styles.actionSuccess, { backgroundColor: colors.success }]} onPress={() => setShowCompleteForm(true)} activeOpacity={0.7} accessibilityRole="button">
                  <Text style={[styles.actionBtnText, { color: colors.onPrimary }]}>完成巡检</Text>
                </TouchableOpacity>
              ) : (
                <View style={styles.completeForm}>
                  <Text style={[styles.completeFormLabel, { color: colors.textPrimary }]}>巡检总结</Text>
                  <TextInput
                    style={[styles.completeFormInput, { backgroundColor: colors.inputBg, borderColor: colors.border, color: colors.textPrimary }]}
                    placeholder="请输入巡检总结..."
                    placeholderTextColor={colors.textSecondary}
                    value={completionNote}
                    onChangeText={setCompletionNote}
                    multiline
                    numberOfLines={3}
                    textAlignVertical="top"
                  />
                  <View style={styles.completeFormActions}>
                    <TouchableOpacity style={[styles.cancelBtn, { backgroundColor: colors.neutralBg }]} onPress={() => { setShowCompleteForm(false); setCompletionNote(''); }} accessibilityRole="button">
                      <Text style={[styles.cancelBtnText, { color: colors.textSecondary }]}>取消</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={[styles.submitCompleteBtn, submitting && { opacity: 0.6 }, { backgroundColor: colors.success }]} onPress={onComplete} disabled={submitting} accessibilityRole="button">
                      {submitting ? <ActivityIndicator color={colors.onPrimary} size="small" /> : <Text style={[styles.submitCompleteBtnText, { color: colors.onPrimary }]}>提交结果</Text>}
                    </TouchableOpacity>
                  </View>
                </View>
              )}
            </>
          )}

          {task?.status === 'completed' && (
            <View style={styles.completedHint}>
              <Text style={[styles.completedHintText, { color: colors.success }]}>✅ 巡检已完成</Text>
            </View>
          )}
        </View>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: 16, paddingBottom: 40 },
  headerCard: { borderRadius: 12, padding: 16, marginBottom: 16, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2 },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 },
  taskTitle: { fontSize: 18, fontWeight: '600', flex: 1, marginRight: 8 },
  headerMeta: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  typeBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
  typeText: { fontSize: 11, fontWeight: '500' },
  headerStation: { fontSize: 13 },
  section: { marginBottom: 16 },
  sectionTitle: { fontSize: 16, fontWeight: '600', marginBottom: 10 },
  infoCard: { borderRadius: 12, padding: 4, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2 },
  infoRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1 },
  infoLabel: { fontSize: 14 },
  infoValue: { fontSize: 14, fontWeight: '500' },
  itemCard: { borderRadius: 10, padding: 14, marginBottom: 8, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.03, shadowRadius: 3, elevation: 1 },
  itemHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  itemName: { fontSize: 14, fontWeight: '500', flex: 1, marginRight: 8 },
  itemResultIcon: { fontSize: 20 },
  itemExpected: { fontSize: 12, marginBottom: 2 },
  itemNote: { fontSize: 12, fontStyle: 'italic' },
  itemActions: { flexDirection: 'row', gap: 6, marginTop: 8 },
  passBtn: { flex: 1, paddingVertical: 8, borderRadius: 6, alignItems: 'center' },
  failBtn: { flex: 1, paddingVertical: 8, borderRadius: 6, alignItems: 'center' },
  naBtn: { flex: 1, paddingVertical: 8, borderRadius: 6, alignItems: 'center' },
  actionBtnText: { fontSize: 13, fontWeight: '500' },
  resultCard: { borderRadius: 12, padding: 16, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2 },
  resultHeader: { marginBottom: 8 },
  resultOverall: { fontSize: 18, fontWeight: '600' },
  resultSummary: { fontSize: 14, lineHeight: 20, marginBottom: 10 },
  resultMeta: { flexDirection: 'row', justifyContent: 'space-between', borderTopWidth: 1, paddingTop: 10 },
  resultMetaText: { fontSize: 12 },
  actionCard: { borderRadius: 12, padding: 16, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2, gap: 10 },
  actionBtn: { borderRadius: 8, paddingVertical: 14, alignItems: 'center' },
  actionPrimary: {},
  actionSuccess: {},
  completeForm: { gap: 10 },
  completeFormLabel: { fontSize: 14, fontWeight: '500' },
  completeFormInput: { borderRadius: 8, borderWidth: 1, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, height: 80 },
  completeFormActions: { flexDirection: 'row', gap: 10 },
  cancelBtn: { flex: 1, paddingVertical: 12, borderRadius: 8, alignItems: 'center' },
  cancelBtnText: { fontSize: 15, fontWeight: '500' },
  submitCompleteBtn: { flex: 2, paddingVertical: 12, borderRadius: 8, alignItems: 'center' },
  submitCompleteBtnText: { fontSize: 15, fontWeight: '600' },
  completedHint: { alignItems: 'center', paddingVertical: 8 },
  completedHintText: { fontSize: 16, fontWeight: '500' },
});

export default InspectionDetailScreen;
