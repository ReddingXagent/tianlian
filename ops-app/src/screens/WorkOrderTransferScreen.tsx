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
import { useTheme } from '../hooks/useTheme';
import { useWorkOrderTransfer } from '../hooks/useWorkOrderTransfer';

const WorkOrderTransferScreen: React.FC = () => {
  const { colors } = useTheme();
  const {
    assigneeId,
    reason,
    localError,
    transferError,
    transferring,
    setAssigneeId,
    setReason,
    clearError,
    handleTransfer,
    handleUrge,
  } = useWorkOrderTransfer();

  const onTransfer = async () => {
    const success = await handleTransfer();
    if (success) {
      Alert.alert('转派成功', `工单已转派给 #${assigneeId}`, [
        { text: '确定' },
      ]);
    }
  };

  const onUrge = () => {
    Alert.alert('催单', '确定要催促工程师处理此工单吗？', [
      { text: '取消', style: 'cancel' },
      {
        text: '确定催单',
        onPress: async () => {
          const success = await handleUrge();
          if (success) {
            Alert.alert('催单成功', '已通知工程师尽快处理');
          }
        },
      },
    ]);
  };

  const onFieldChange = (setter: (t: string) => void) => (t: string) => {
    setter(t);
    clearError();
  };

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.pageBg }]}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>工单流转</Text>

      {(localError || transferError) && (
        <View style={[styles.errorContainer, { backgroundColor: colors.errorBg }]}>
          <Text style={[styles.errorText, { color: colors.error }]}>{localError || transferError}</Text>
        </View>
      )}

      {/* 转派区域 */}
      <View style={styles.section}>
        <Text style={[styles.sectionLabel, { color: colors.textPrimary }]}>转派工单</Text>
        <View style={[styles.card, { backgroundColor: colors.cardBg }]}>
          <Text style={[styles.fieldLabel, { color: colors.textSecondary }]}>目标运维人员ID</Text>
          <TextInput
            testID="workorder-transfer-assignee-input"
            style={[styles.input, { backgroundColor: colors.inputBg, borderColor: colors.border, color: colors.textPrimary }]}
            placeholder="请输入运维人员ID"
            placeholderTextColor={colors.textSecondary}
            value={assigneeId}
            onChangeText={onFieldChange(setAssigneeId)}
            keyboardType="numeric"
            editable={!transferring}
          />

          <Text style={[styles.fieldLabel, { color: colors.textSecondary }]}>转派原因</Text>
          <TextInput
            testID="workorder-transfer-reason-input"
            style={[styles.input, styles.textArea, { backgroundColor: colors.inputBg, borderColor: colors.border, color: colors.textPrimary }]}
            placeholder="请输入转派原因"
            placeholderTextColor={colors.textSecondary}
            value={reason}
            onChangeText={onFieldChange(setReason)}
            multiline
            numberOfLines={3}
            textAlignVertical="top"
            editable={!transferring}
            maxLength={200}
          />

          <TouchableOpacity
            testID="workorder-transfer-submit-btn"
            style={[styles.transferBtn, transferring && styles.btnDisabled, { backgroundColor: colors.primary }]}
            onPress={onTransfer}
            disabled={transferring}
            activeOpacity={0.7}
           accessibilityRole="button">
            {transferring ? (
              <ActivityIndicator color={colors.onPrimary} size="small" />
            ) : (
              <Text style={[styles.btnText, { color: colors.onPrimary }]}>转派工单</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>

      {/* 催单区域 */}
      <View style={styles.section}>
        <Text style={[styles.sectionLabel, { color: colors.textPrimary }]}>催单</Text>
        <View style={[styles.card, { backgroundColor: colors.cardBg }]}>
          <Text style={[styles.hintText, { color: colors.textSecondary }]}>
            催单后将通知工程师尽快处理，适用于工单长时间未接单或未完成的场景。
          </Text>
          <TouchableOpacity
            testID="workorder-transfer-urge-btn"
            style={[styles.escalateBtn, transferring && styles.btnDisabled, { backgroundColor: colors.warning }]}
            onPress={onUrge}
            disabled={transferring}
            activeOpacity={0.7}
           accessibilityRole="button">
            {transferring ? (
              <ActivityIndicator color={colors.onPrimary} size="small" />
            ) : (
              <Text style={[styles.btnText, { color: colors.onPrimary }]}>催促处理</Text>
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
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 20,
  },
  errorContainer: {
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
  },
  errorText: {
    fontSize: 14,
    textAlign: 'center',
  },
  section: {
    marginBottom: 20,
  },
  sectionLabel: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 10,
  },
  card: {
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
    marginBottom: 6,
    marginTop: 12,
  },
  input: {
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
  },
  textArea: {
    height: 80,
    paddingTop: 10,
  },
  hintText: {
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 16,
  },
  transferBtn: {
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 16,
  },
  escalateBtn: {
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
  },
  btnDisabled: {
    opacity: 0.6,
  },
  btnText: {
    fontSize: 16,
    fontWeight: '600',
  },
});

export default WorkOrderTransferScreen;
