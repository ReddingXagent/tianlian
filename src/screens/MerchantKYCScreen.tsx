/**
 * MerchantKYCScreen — 商户进件 (服务商特约商户 KYC) 申请与状态跟踪
 * 卡 a8ca56aa: 云端契约未定, 默认 mock 通道; 表单(6字段+4证照) → 状态视图(四态+驳回重提)
 */
import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { useTheme } from '../hooks/useTheme';
import { useMerchantApplication } from '../hooks/useMerchantApplication';
import { merchantStatusLabel } from '../services/merchant';
import { MERCHANT_KYC_MODE, merchantKycModeLabel } from '../services/merchant-source';
import type { MerchantApplicationStatus } from '../types';
import {
  EMPTY_MERCHANT_FORM,
  MERCHANT_PHOTO_SLOTS,
  MERCHANT_TEXT_FIELDS,
  pickMockPhotoUri,
  validateMerchantForm,
  type MerchantFormErrors,
  type MerchantPhotoSlotKey,
  type MerchantTextFieldKey,
} from '../utils/merchant-kyc';

const STATUS_COLOR: Record<MerchantApplicationStatus, string> = {
  pending: 'warning',
  audit: 'info',
  rejected: 'error',
  approved: 'success',
};

const formatTimestamp = (iso: string): string => iso.slice(0, 19).replace('T', ' ');

const MerchantKYCScreen: React.FC = () => {
  const { colors } = useTheme();
  const { application, loading, submitting, error, submit, refresh, backToForm } = useMerchantApplication();
  const [form, setForm] = useState(EMPTY_MERCHANT_FORM);
  const [errors, setErrors] = useState<MerchantFormErrors>({});

  const setTextField = (key: MerchantTextFieldKey, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const pickPhoto = (slot: MerchantPhotoSlotKey) => {
    setForm((prev) => ({ ...prev, photos: { ...prev.photos, [slot]: pickMockPhotoUri(slot) } }));
  };

  const handleSubmit = async () => {
    const errs = validateMerchantForm(form);
    setErrors(errs);
    if (Object.keys(errs).length > 0) return;
    await submit(form);
  };

  const formView = (
    <ScrollView style={[styles.container, { backgroundColor: colors.pageBg }]} contentContainerStyle={styles.content}>
      <Text style={[styles.modeHint, { color: colors.textMuted }]}>
        数据通道：{merchantKycModeLabel(MERCHANT_KYC_MODE)}
      </Text>

      {MERCHANT_TEXT_FIELDS.map((f) => (
        <View key={f.key} style={styles.fieldBlock}>
          <Text style={[styles.fieldLabel, { color: colors.textSecondary }]}>{f.label}</Text>
          <TextInput
            style={[styles.input, { backgroundColor: colors.cardBg, color: colors.textPrimary, borderColor: colors.divider }]}
            placeholder={f.placeholder}
            placeholderTextColor={colors.textMuted}
            value={form[f.key]}
            onChangeText={(t) => setTextField(f.key, t)}
            testID={f.testID}
            autoCapitalize="characters"
          />
          {errors[f.key] ? (
            <Text style={[styles.fieldError, { color: colors.error }]} testID={`kyc-err-${f.key}`}>
              {errors[f.key]}
            </Text>
          ) : null}
        </View>
      ))}

      <Text style={[styles.sectionLabel, { color: colors.textSecondary }]}>证照上传</Text>
      <View style={styles.photoGrid}>
        {MERCHANT_PHOTO_SLOTS.map((slot) => (
          <TouchableOpacity
            key={slot.key}
            style={[styles.photoSlot, { backgroundColor: colors.cardBg, borderColor: colors.divider }]}
            activeOpacity={0.6}
            onPress={() => pickPhoto(slot.key)}
            testID={slot.testID}
            accessibilityRole="button"
          >
            <Text style={styles.photoIcon}>📷</Text>
            <Text style={[styles.photoLabel, { color: colors.textPrimary }]}>{slot.label}</Text>
            <Text style={[styles.photoState, { color: form.photos[slot.key] ? colors.success : colors.textMuted }]}>
              {form.photos[slot.key] ? '已选择' : '点击上传'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
      {errors.photos ? (
        <Text style={[styles.fieldError, { color: colors.error }]} testID="kyc-err-photos">
          {errors.photos}
        </Text>
      ) : null}

      {error ? (
        <Text style={[styles.submitError, { color: colors.error }]} testID="kyc-error-text">
          {error}
        </Text>
      ) : null}

      <TouchableOpacity
        style={[styles.submitButton, { backgroundColor: colors.primary }]}
        activeOpacity={0.7}
        onPress={handleSubmit}
        disabled={submitting}
        testID="kyc-submit-btn"
        accessibilityRole="button"
      >
        {submitting ? (
          <ActivityIndicator color={colors.onPrimary} />
        ) : (
          <Text style={[styles.submitText, { color: colors.onPrimary }]}>提交进件申请</Text>
        )}
      </TouchableOpacity>
    </ScrollView>
  );

  const statusView = application && (
    <ScrollView style={[styles.container, { backgroundColor: colors.pageBg }]} contentContainerStyle={styles.content}>
      <View style={[styles.statusCard, { backgroundColor: colors.cardBg }]} testID="kyc-status-card">
        <Text style={[styles.statusBadge, { color: colors[STATUS_COLOR[application.status] as 'success'] }]}>
          {merchantStatusLabel(application.status)}
        </Text>
        <Text style={[styles.statusId, { color: colors.textSecondary }]}>申请编号：{application.id}</Text>
        <Text style={[styles.statusMeta, { color: colors.textSecondary }]}>
          提交时间：{formatTimestamp(application.submittedAt)}
        </Text>
        <Text style={[styles.statusMeta, { color: colors.textSecondary }]}>
          更新时间：{formatTimestamp(application.updatedAt)}
        </Text>
        {application.status === 'rejected' && application.rejectReason ? (
          <Text style={[styles.rejectReason, { color: colors.error }]} testID="kyc-reject-reason">
            驳回原因：{application.rejectReason}
          </Text>
        ) : null}
        {application.status === 'approved' ? (
          <Text style={[styles.approvedHint, { color: colors.success }]} testID="kyc-approved-hint">
            进件已通过，结算账户开通后即可收款
          </Text>
        ) : null}
      </View>

      {error ? (
        <Text style={[styles.submitError, { color: colors.error }]} testID="kyc-error-text">
          {error}
        </Text>
      ) : null}

      <TouchableOpacity
        style={[styles.submitButton, { backgroundColor: colors.primary }]}
        activeOpacity={0.7}
        onPress={() => refresh(application.id)}
        disabled={loading}
        testID="kyc-refresh-btn"
        accessibilityRole="button"
      >
        {loading ? (
          <ActivityIndicator color={colors.onPrimary} />
        ) : (
          <Text style={[styles.submitText, { color: colors.onPrimary }]}>刷新状态</Text>
        )}
      </TouchableOpacity>

      {application.status === 'rejected' ? (
        <TouchableOpacity
          style={[styles.resubmitButton, { borderColor: colors.primary }]}
          activeOpacity={0.7}
          onPress={() => {
            setForm({ ...application.form, photos: { ...application.form.photos } });
            backToForm();
          }}
          testID="kyc-resubmit-btn"
          accessibilityRole="button"
        >
          <Text style={[styles.resubmitText, { color: colors.primary }]}>驳回后重新提交</Text>
        </TouchableOpacity>
      ) : null}
    </ScrollView>
  );

  return <View style={[styles.flex, { backgroundColor: colors.pageBg }]}>{application ? statusView : formView}</View>;
};

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: { flex: 1 },
  content: { padding: 16, paddingBottom: 40 },
  modeHint: { fontSize: 12, marginBottom: 12 },
  fieldBlock: { marginBottom: 14 },
  fieldLabel: { fontSize: 13, marginBottom: 6 },
  input: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, fontSize: 15 },
  fieldError: { fontSize: 12, marginTop: 4 },
  sectionLabel: { fontSize: 13, marginBottom: 10, marginTop: 6 },
  photoGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
  photoSlot: {
    width: '48%',
    borderWidth: 1,
    borderStyle: 'dashed',
    borderRadius: 8,
    alignItems: 'center',
    paddingVertical: 14,
    marginBottom: 12,
  },
  photoIcon: { fontSize: 22, marginBottom: 4 },
  photoLabel: { fontSize: 13, fontWeight: '500' },
  photoState: { fontSize: 12, marginTop: 4 },
  submitError: { fontSize: 13, marginTop: 8 },
  submitButton: { borderRadius: 8, paddingVertical: 13, alignItems: 'center', marginTop: 10 },
  submitText: { fontSize: 15, fontWeight: '600' },
  statusCard: { borderRadius: 10, padding: 18 },
  statusBadge: { fontSize: 20, fontWeight: '700', marginBottom: 10 },
  statusId: { fontSize: 14, marginBottom: 6 },
  statusMeta: { fontSize: 13, marginBottom: 4 },
  rejectReason: { fontSize: 13, marginTop: 10 },
  approvedHint: { fontSize: 13, marginTop: 10 },
  resubmitButton: { borderWidth: 1, borderRadius: 8, paddingVertical: 12, alignItems: 'center', marginTop: 12 },
  resubmitText: { fontSize: 15, fontWeight: '600' },
});

export default MerchantKYCScreen;
