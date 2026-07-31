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
  TextInput,
} from 'react-native';
import { useRoute, RouteProp } from '@react-navigation/native';
import { useInspectionStore } from '../store/inspectionStore';
import { RootStackParamList, InspectionTask, InspectionItem } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';

type DetailRouteProp = RouteProp<RootStackParamList, 'InspectionDetail'>;

const TYPE_LABELS: Record<string, string> = {
  daily: '日检', weekly: '周检', monthly: '月检', quarterly: '季检', annual: '年检', special: '特检',
};

const InspectionDetailScreen: React.FC = () => {
  const route = useRoute<DetailRouteProp>();
  const { taskId } = route.params;
  const {
    selectedTask,
    loading,
    error,
    submitting,
    fetchTaskDetail,
    startTask,
    updateItem,
    completeTask,
  } = useInspectionStore();

  const [refreshing, setRefreshing] = useState(false);
  const [completionNote, setCompletionNote] = useState('');
  const [showCompleteForm, setShowCompleteForm] = useState(false);

  const loadData = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) setRefreshing(true);
      await fetchTaskDetail(taskId);
      if (isRefresh) setRefreshing(false);
    },
    [taskId, fetchTaskDetail]
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData();
  }, [taskId, loadData]);

  const handleStart = () => {
    Alert.alert('开始巡检', '确定要开始执行此巡检任务吗？', [
      { text: '取消', style: 'cancel' },
      { text: '确定', onPress: () => startTask(taskId) },
    ]);
  };

  const handleItemResult = (item: InspectionItem, result: 'pass' | 'fail' | 'na') => {
    updateItem(taskId, item.id, result);
  };

  const handleComplete = async () => {
    if (!completionNote.trim()) {
      Alert.alert('提示', '请填写巡检总结');
      return;
    }
    const passedCount = selectedTask?.items.filter((i) => i.result === 'pass').length || 0;
    const totalCount = selectedTask?.items.length || 1;
    const overall = passedCount === totalCount ? 'pass' : passedCount > 0 ? 'partial' : 'fail';
    await completeTask(taskId, completionNote.trim(), overall);
    setShowCompleteForm(false);
    setCompletionNote('');
  };

  const getResultIcon = (result?: string) => {
    switch (result) {
      case 'pass': return '✅';
      case 'fail': return '❌';
      case 'na': return '➖';
      default: return '⬜';
    }
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
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => loadData(true)} colors={['#1a73e8']} tintColor="#1a73e8" />
      }
    >
      {/* Header */}
      <View style={styles.headerCard}>
        <View style={styles.headerRow}>
          <Text style={styles.taskTitle} numberOfLines={2}>{task?.description}</Text>
          <StatusBadge status={task?.status ?? 'pending'} />
        </View>
        <View style={styles.headerMeta}>
          <View style={styles.typeBadge}>
            <Text style={styles.typeText}>{TYPE_LABELS[task?.type ?? 'daily'] || task?.type}</Text>
          </View>
          <Text style={styles.headerStation}>{task?.stationName}</Text>
        </View>
      </View>

      {/* Info */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>基本信息</Text>
        <View style={styles.infoCard}>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>设备名称</Text>
            <Text style={styles.infoValue}>{task?.deviceName || '-'}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>计划日期</Text>
            <Text style={styles.infoValue}>{task?.scheduledDate ? new Date(task.scheduledDate).toLocaleDateString('zh-CN') : '-'}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>负责人</Text>
            <Text style={styles.infoValue}>{task?.assignedName || '未分配'}</Text>
          </View>
          <View style={[styles.infoRow, { borderBottomWidth: 0 }]}>
            <Text style={styles.infoLabel}>完成日期</Text>
            <Text style={styles.infoValue}>{task?.completedDate ? new Date(task.completedDate).toLocaleDateString('zh-CN') : '-'}</Text>
          </View>
        </View>
      </View>

      {/* Inspection Items */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>检查项目 ({task?.items?.length || 0})</Text>
        {task?.items?.map((item) => (
          <View key={item.id} style={styles.itemCard}>
            <View style={styles.itemHeader}>
              <Text style={styles.itemName} numberOfLines={2}>{item.name}</Text>
              <Text style={styles.itemResultIcon}>{getResultIcon(item.result)}</Text>
            </View>
            <Text style={styles.itemExpected}>标准: {item.expected}</Text>
            {item.note && <Text style={styles.itemNote}>备注: {item.note}</Text>}

            {task.status === 'in_progress' && !item.result && (
              <View style={styles.itemActions}>
                <TouchableOpacity style={styles.passBtn} onPress={() => handleItemResult(item, 'pass')} disabled={submitting}>
                  <Text style={styles.actionBtnText}>✅ 通过</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.failBtn} onPress={() => handleItemResult(item, 'fail')} disabled={submitting}>
                  <Text style={styles.actionBtnText}>❌ 不通过</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.naBtn} onPress={() => handleItemResult(item, 'na')} disabled={submitting}>
                  <Text style={styles.actionBtnText}>N/A</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        ))}
      </View>

      {/* Result summary */}
      {task?.result && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>巡检结果</Text>
          <View style={styles.resultCard}>
            <View style={styles.resultHeader}>
              <Text style={styles.resultOverall}>
                {task.result.overall === 'pass' ? '✅ 通过' : task.result.overall === 'partial' ? '⚠️ 部分通过' : '❌ 未通过'}
              </Text>
            </View>
            <Text style={styles.resultSummary}>{task.result.summary}</Text>
            <View style={styles.resultMeta}>
              <Text style={styles.resultMetaText}>操作人: {task.result.operatorName}</Text>
              <Text style={styles.resultMetaText}>{new Date(task.result.completedAt).toLocaleString('zh-CN')}</Text>
            </View>
          </View>
        </View>
      )}

      {/* Actions */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>操作</Text>
        <View style={styles.actionCard}>
          {task?.status === 'pending' && (
            <TouchableOpacity style={[styles.actionBtn, styles.actionPrimary]} onPress={handleStart} disabled={submitting} activeOpacity={0.7}>
              {submitting ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.actionBtnText}>开始巡检</Text>}
            </TouchableOpacity>
          )}

          {task?.status === 'in_progress' && (
            <>
              {!showCompleteForm ? (
                <TouchableOpacity style={[styles.actionBtn, styles.actionSuccess]} onPress={() => setShowCompleteForm(true)} activeOpacity={0.7}>
                  <Text style={styles.actionBtnText}>完成巡检</Text>
                </TouchableOpacity>
              ) : (
                <View style={styles.completeForm}>
                  <Text style={styles.completeFormLabel}>巡检总结</Text>
                  <TextInput
                    style={styles.completeFormInput}
                    placeholder="请输入巡检总结..."
                    placeholderTextColor="#999"
                    value={completionNote}
                    onChangeText={setCompletionNote}
                    multiline
                    numberOfLines={3}
                    textAlignVertical="top"
                  />
                  <View style={styles.completeFormActions}>
                    <TouchableOpacity style={styles.cancelBtn} onPress={() => { setShowCompleteForm(false); setCompletionNote(''); }}>
                      <Text style={styles.cancelBtnText}>取消</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={[styles.submitCompleteBtn, submitting && { opacity: 0.6 }]} onPress={handleComplete} disabled={submitting}>
                      {submitting ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.submitCompleteBtnText}>提交结果</Text>}
                    </TouchableOpacity>
                  </View>
                </View>
              )}
            </>
          )}

          {task?.status === 'completed' && (
            <View style={styles.completedHint}>
              <Text style={styles.completedHintText}>✅ 巡检已完成</Text>
            </View>
          )}
        </View>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f6fa' },
  content: { padding: 16, paddingBottom: 40 },
  headerCard: { backgroundColor: '#fff', borderRadius: 12, padding: 16, marginBottom: 16, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2 },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 },
  taskTitle: { fontSize: 18, fontWeight: '600', color: '#333', flex: 1, marginRight: 8 },
  headerMeta: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  typeBadge: { paddingHorizontal: 8, paddingVertical: 2, backgroundColor: '#e3f2fd', borderRadius: 4 },
  typeText: { fontSize: 11, color: '#1565c0', fontWeight: '500' },
  headerStation: { fontSize: 13, color: '#999' },
  section: { marginBottom: 16 },
  sectionTitle: { fontSize: 16, fontWeight: '600', color: '#333', marginBottom: 10 },
  infoCard: { backgroundColor: '#fff', borderRadius: 12, padding: 4, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2 },
  infoRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#f0f0f0' },
  infoLabel: { fontSize: 14, color: '#999' },
  infoValue: { fontSize: 14, color: '#333', fontWeight: '500' },
  itemCard: { backgroundColor: '#fff', borderRadius: 10, padding: 14, marginBottom: 8, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.03, shadowRadius: 3, elevation: 1 },
  itemHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  itemName: { fontSize: 14, fontWeight: '500', color: '#333', flex: 1, marginRight: 8 },
  itemResultIcon: { fontSize: 20 },
  itemExpected: { fontSize: 12, color: '#999', marginBottom: 2 },
  itemNote: { fontSize: 12, color: '#666', fontStyle: 'italic' },
  itemActions: { flexDirection: 'row', gap: 6, marginTop: 8 },
  passBtn: { flex: 1, paddingVertical: 8, backgroundColor: '#e8f5e9', borderRadius: 6, alignItems: 'center' },
  failBtn: { flex: 1, paddingVertical: 8, backgroundColor: '#fce4ec', borderRadius: 6, alignItems: 'center' },
  naBtn: { flex: 1, paddingVertical: 8, backgroundColor: '#f5f5f5', borderRadius: 6, alignItems: 'center' },
  actionBtnText: { fontSize: 13, fontWeight: '500', color: '#333' },
  resultCard: { backgroundColor: '#fff', borderRadius: 12, padding: 16, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2 },
  resultHeader: { marginBottom: 8 },
  resultOverall: { fontSize: 18, fontWeight: '600', color: '#333' },
  resultSummary: { fontSize: 14, color: '#666', lineHeight: 20, marginBottom: 10 },
  resultMeta: { flexDirection: 'row', justifyContent: 'space-between', borderTopWidth: 1, borderTopColor: '#f0f0f0', paddingTop: 10 },
  resultMetaText: { fontSize: 12, color: '#999' },
  actionCard: { backgroundColor: '#fff', borderRadius: 12, padding: 16, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2, gap: 10 },
  actionBtn: { borderRadius: 8, paddingVertical: 14, alignItems: 'center' },
  actionPrimary: { backgroundColor: '#1a73e8' },
  actionSuccess: { backgroundColor: '#2e7d32' },
  completeForm: { gap: 10 },
  completeFormLabel: { fontSize: 14, fontWeight: '500', color: '#333' },
  completeFormInput: { backgroundColor: '#fafafa', borderRadius: 8, borderWidth: 1, borderColor: '#ddd', paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, color: '#333', height: 80 },
  completeFormActions: { flexDirection: 'row', gap: 10 },
  cancelBtn: { flex: 1, paddingVertical: 12, borderRadius: 8, alignItems: 'center', backgroundColor: '#f5f5f5' },
  cancelBtnText: { fontSize: 15, color: '#666', fontWeight: '500' },
  submitCompleteBtn: { flex: 2, paddingVertical: 12, borderRadius: 8, alignItems: 'center', backgroundColor: '#2e7d32' },
  submitCompleteBtnText: { color: '#fff', fontSize: 15, fontWeight: '600' },
  completedHint: { alignItems: 'center', paddingVertical: 8 },
  completedHintText: { fontSize: 16, fontWeight: '500', color: '#2e7d32' },
});

export default InspectionDetailScreen;
