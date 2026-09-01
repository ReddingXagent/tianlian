import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useWorkOrderCreate } from '../hooks/useWorkOrderCreate';
import { useTheme } from '../hooks/useTheme';
import { RootStackParamList, WorkOrderType, WorkOrderPriority } from '../types';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const ORDER_TYPES: { key: WorkOrderType; label: string }[] = [
  { key: 'repair', label: '维修' },
  { key: 'inspection', label: '巡检' },
  { key: 'installation', label: '安装' },
  { key: 'maintenance', label: '保养' },
  { key: 'other', label: '其他' },
];

const PRIORITIES: {
  key: WorkOrderPriority;
  label: string;
  color: 'success' | 'info' | 'error';
}[] = [
  { key: 'low', label: '低', color: 'success' },
  { key: 'normal', label: '中', color: 'info' },
  { key: 'high', label: '高', color: 'error' },
  { key: 'urgent', label: '紧急', color: 'error' },
];

const WorkOrderCreateScreen: React.FC = () => {
  const navigation = useNavigation<NavigationProp>();
  const { colors } = useTheme();
  const {
    title, description, stationId, type, priority,
    localError, createError, creating,
    setTitle, setDescription, setStationId, setType, setPriority,
    clearError, handleSubmit,
  } = useWorkOrderCreate();

  const onSubmit = async () => {
    const order = await handleSubmit();
    if (order) {
      Alert.alert('创建成功', `工单 #${order.id} 已创建`, [
        { text: '查看详情', onPress: () => navigation.replace('WorkOrderDetail', { orderId: order.id }) },
        { text: '继续创建', onPress: () => { /* form already reset by hook */ } },
      ]);
    }
  };

  const onFieldChange = (setter: (t: string) => void) => (t: string) => {
    setter(t);
    clearError();
  };

  return (
    <KeyboardAvoidingView
      style={[styles.container, { backgroundColor: colors.pageBg }]}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>创建工单</Text>

        {(localError || createError) && (
          <View style={[styles.errorContainer, { backgroundColor: colors.errorBg }]}>
            <Text style={[styles.errorText, { color: colors.error }]}>{localError || createError}</Text>
          </View>
        )}

        {/* 工单标题 */}
        <View style={styles.fieldGroup}>
          <Text style={[styles.label, { color: colors.textPrimary }]}>工单标题 *</Text>
          <TextInput
            style={[styles.input, { backgroundColor: colors.cardBg, borderColor: colors.border, color: colors.textPrimary }]}
            placeholder="请输入工单标题"
            placeholderTextColor={colors.textSecondary}
            value={title}
            onChangeText={onFieldChange(setTitle)}
            editable={!creating}
            maxLength={100}
          />
        </View>

        {/* 工单描述 */}
        <View style={styles.fieldGroup}>
          <Text style={[styles.label, { color: colors.textPrimary }]}>工单描述 *</Text>
          <TextInput
            style={[styles.input, styles.textArea, { backgroundColor: colors.cardBg, borderColor: colors.border, color: colors.textPrimary }]}
            placeholder="请详细描述工单内容"
            placeholderTextColor={colors.textSecondary}
            value={description}
            onChangeText={onFieldChange(setDescription)}
            multiline
            numberOfLines={4}
            textAlignVertical="top"
            editable={!creating}
            maxLength={500}
          />
        </View>

        {/* 站点ID */}
        <View style={styles.fieldGroup}>
          <Text style={[styles.label, { color: colors.textPrimary }]}>关联站点ID *</Text>
          <TextInput
            style={[styles.input, { backgroundColor: colors.cardBg, borderColor: colors.border, color: colors.textPrimary }]}
            placeholder="请输入站点ID"
            placeholderTextColor={colors.textSecondary}
            value={stationId}
            onChangeText={onFieldChange(setStationId)}
            keyboardType="numeric"
            editable={!creating}
          />
        </View>

        {/* 工单类型 */}
        <View style={styles.fieldGroup}>
          <Text style={[styles.label, { color: colors.textPrimary }]}>工单类型</Text>
          <View style={styles.chipContainer}>
            {ORDER_TYPES.map((ot) => (
              <TouchableOpacity
                key={ot.key}
                style={[styles.chip, { backgroundColor: colors.neutralBg }, type === ot.key && { backgroundColor: colors.primary }]}
                onPress={() => setType(ot.key)}
                disabled={creating}
               accessibilityRole="button">
                <Text style={[styles.chipText, { color: colors.textSecondary }, type === ot.key && { color: colors.onPrimary }]}>
                  {ot.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* 优先级 */}
        <View style={styles.fieldGroup}>
          <Text style={[styles.label, { color: colors.textPrimary }]}>优先级</Text>
          <View style={styles.chipContainer}>
            {PRIORITIES.map((p) => (
              <TouchableOpacity
                key={p.key}
                style={[
                  styles.chip,
                  { backgroundColor: colors.neutralBg },
                  priority === p.key && { backgroundColor: colors[p.color] },
                ]}
                onPress={() => setPriority(p.key)}
                disabled={creating}
               accessibilityRole="button">
                <Text
                  style={[
                    styles.chipText,
                    { color: colors.textSecondary },
                    priority === p.key && { color: colors.onPrimary },
                  ]}
                >
                  {p.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* 提交按钮 */}
        <TouchableOpacity
          style={[styles.submitBtn, creating && styles.submitBtnDisabled, { backgroundColor: colors.primary }]}
          onPress={onSubmit}
          disabled={creating}
          activeOpacity={0.7}
         accessibilityRole="button">
          {creating ? (
            <ActivityIndicator color={colors.onPrimary} size="small" />
          ) : (
            <Text style={[styles.submitBtnText, { color: colors.onPrimary }]}>提交工单</Text>
          )}
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scrollView: {
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
  fieldGroup: {
    marginBottom: 20,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  input: {
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
  },
  textArea: {
    height: 100,
    paddingTop: 12,
  },
  chipContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  chip: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
  },
  chipText: {
    fontSize: 14,
    fontWeight: '500',
  },
  submitBtn: {
    borderRadius: 10,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 10,
  },
  submitBtnDisabled: {
    opacity: 0.6,
  },
  submitBtnText: {
    fontSize: 17,
    fontWeight: '600',
  },
});

export default WorkOrderCreateScreen;
