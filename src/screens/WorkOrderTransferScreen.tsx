import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { useRoute, RouteProp } from '@react-navigation/native';
import { useWorkOrderEnhancedStore } from '../store/workOrderEnhancedStore';
import { RootStackParamList } from '../types';

type TransferRouteProp = RouteProp<RootStackParamList, 'WorkOrderDetail'>;

const WorkOrderTransferScreen: React.FC = () => {
  const route = useRoute<TransferRouteProp>();
  const { orderId } = route.params;
  const { transferring, transferError, transferOrder, escalateOrder } =
    useWorkOrderEnhancedStore();

  const [assigneeId, setAssigneeId] = useState('');
  const [reason, setReason] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);

  const handleTransfer = async () => {
    setLocalError(null);

    if (!assigneeId.trim() || isNaN(Number(assigneeId))) {
      setLocalError('请输入有效的运维人员ID');
      return;
    }
    if (!reason.trim()) {
      setLocalError('请输入转派原因');
      return;
    }

    const result = await transferOrder(orderId, Number(assigneeId), reason.trim());
    if (result) {
      Alert.alert('转派成功', `工单已转派给 #${assigneeId}`, [
        { text: '确定' },
      ]);
    }
  };

  const handleEscalate = () => {
    Alert.alert('升级工单', '确定要将此工单升级吗？升级后工单将提交给上级处理。', [
      { text: '取消', style: 'cancel' },
      {
        text: '确定升级',
        style: 'destructive',
        onPress: async () => {
          const reason = '需要上级协助处理';
          const result = await escalateOrder(orderId, reason);
          if (result) {
            Alert.alert('升级成功', '工单已升级，等待上级处理');
          }
        },
      },
    ]);
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <Text style={styles.sectionTitle}>工单流转</Text>

      {(localError || transferError) && (
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>{localError || transferError}</Text>
        </View>
      )}

      {/* 转派区域 */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>转派工单</Text>
        <View style={styles.card}>
          <Text style={styles.fieldLabel}>目标运维人员ID</Text>
          <TextInput
            style={styles.input}
            placeholder="请输入运维人员ID"
            placeholderTextColor="#999"
            value={assigneeId}
            onChangeText={(t) => { setAssigneeId(t); setLocalError(null); }}
            keyboardType="numeric"
            editable={!transferring}
          />

          <Text style={styles.fieldLabel}>转派原因</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            placeholder="请输入转派原因"
            placeholderTextColor="#999"
            value={reason}
            onChangeText={(t) => { setReason(t); setLocalError(null); }}
            multiline
            numberOfLines={3}
            textAlignVertical="top"
            editable={!transferring}
            maxLength={200}
          />

          <TouchableOpacity
            style={[styles.transferBtn, transferring && styles.btnDisabled]}
            onPress={handleTransfer}
            disabled={transferring}
            activeOpacity={0.7}
          >
            {transferring ? (
              <ActivityIndicator color="#fff" size="small" />
            ) : (
              <Text style={styles.btnText}>转派工单</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>

      {/* 升级区域 */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>升级工单</Text>
        <View style={styles.card}>
          <Text style={styles.hintText}>
            升级后工单将提交给上级主管处理，适用于遇到无法解决的问题或需要更高级别资源支持的情况。
          </Text>
          <TouchableOpacity
            style={[styles.escalateBtn, transferring && styles.btnDisabled]}
            onPress={handleEscalate}
            disabled={transferring}
            activeOpacity={0.7}
          >
            {transferring ? (
              <ActivityIndicator color="#fff" size="small" />
            ) : (
              <Text style={styles.btnText}>升级工单</Text>
            )}
          </TouchableOpacity>
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
  sectionTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#333',
    marginBottom: 20,
  },
  errorContainer: {
    backgroundColor: '#fce4ec',
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
  },
  errorText: {
    color: '#c62828',
    fontSize: 14,
    textAlign: 'center',
  },
  section: {
    marginBottom: 20,
  },
  sectionLabel: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    marginBottom: 10,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: '500',
    color: '#666',
    marginBottom: 6,
    marginTop: 12,
  },
  input: {
    backgroundColor: '#fafafa',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#ddd',
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    color: '#333',
  },
  textArea: {
    height: 80,
    paddingTop: 10,
  },
  hintText: {
    fontSize: 14,
    color: '#666',
    lineHeight: 20,
    marginBottom: 16,
  },
  transferBtn: {
    backgroundColor: '#1a73e8',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 16,
  },
  escalateBtn: {
    backgroundColor: '#e65100',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
  },
  btnDisabled: {
    opacity: 0.6,
  },
  btnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});

export default WorkOrderTransferScreen;
