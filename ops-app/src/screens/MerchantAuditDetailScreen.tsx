/**
 * MerchantAuditDetailScreen.tsx — 商户进件审核详情 (卡 a8ca56aa ops-app 审核侧)
 * 查看运营商提交的证照+结算账户信息, 对 pending/audit 单执行批准/驳回;
 * rejected 单展示驳回原因 (由 station-app 重提产生新单).
 */
import { useCallback, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
} from 'react-native';
import { useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import { merchantAudit } from '../services/api-modules/merchant-audit-source';
import {
  MerchantApplication,
  MERCHANT_STATUS_LABEL,
  RootStackParamList,
} from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import { usePolling } from '../hooks/usePolling';
import { useTheme } from '../hooks/useTheme';

type DetailRoute = RouteProp<RootStackParamList, 'MerchantAuditDetail'>;

const STATUS_BADGE_KEY: Record<MerchantApplication['status'], string> = {
  pending: 'pending',
  audit: 'processing',
  rejected: 'cancelled',
  approved: 'completed',
};

const PHOTO_SLOTS: { key: keyof MerchantApplication['form']['photos']; label: string }[] = [
  { key: 'license', label: '营业执照' },
  { key: 'idCardFront', label: '身份证正面' },
  { key: 'idCardBack', label: '身份证反面' },
  { key: 'bankCard', label: '银行卡照片' },
];

const FIELD_ROWS: { key: keyof MerchantApplication['form']; label: string }[] = [
  { key: 'companyName', label: '企业名称' },
  { key: 'uscc', label: '统一社会信用代码' },
  { key: 'contactName', label: '联系人' },
  { key: 'contactPhone', label: '联系电话' },
  { key: 'bankName', label: '开户银行' },
  { key: 'bankAccount', label: '结算账号' },
];

const MerchantAuditDetailScreen: React.FC = () => {
  const route = useRoute<DetailRoute>();
  const { applicationId } = route.params;
  const { colors } = useTheme();
  const [rejectReason, setRejectReason] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const fetcher = useCallback(async () => {
    const app = await merchantAudit.getApplication(applicationId);
    return app;
  }, [applicationId]);

  const { data, loading, error, refresh } = usePolling(fetcher, {
    interval: 15_000,
    enabled: true,
  });

  const handleApprove = async () => {
    setSubmitting(true);
    setActionError(null);
    try {
      await merchantAudit.approve(applicationId);
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : '批准失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReject = async () => {
    const reason = rejectReason.trim();
    if (!reason) {
      setActionError('请填写驳回原因');
      return;
    }
    setSubmitting(true);
    setActionError(null);
    try {
      await merchantAudit.reject(applicationId, reason);
      setRejectReason('');
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : '驳回失败');
    } finally {
      setSubmitting(false);
    }
  };

  const confirmApprove = () => {
    Alert.alert('确认批准', '批准后该商户进入结算开通流程，确认操作？', [
      { text: '取消', style: 'cancel' },
      { text: '确认批准', onPress: handleApprove },
    ]);
  };

  if (loading && !data) {
    return <LoadingSpinner text="加载进件详情..." />;
  }

  if (error && !data) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error.message}
        actionLabel="重新加载"
        onAction={refresh}
      />
    );
  }

  if (!data) {
    return (
      <EmptyState
        icon="🏦"
        title="申请不存在"
        message="该进件申请可能已被撤回"
        actionLabel="重新加载"
        onAction={refresh}
      />
    );
  }

  const auditable = data.status === 'pending' || data.status === 'audit';

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.pageBg }]}
      contentContainerStyle={styles.content}
    >
      <View style={[styles.card, { backgroundColor: colors.cardBg }]}>
        <View style={styles.headerRow}>
          <Text style={[styles.companyName, { color: colors.textPrimary }]}>
            {data.form.companyName || `申请 #${data.id}`}
          </Text>
          <StatusBadge
            status={STATUS_BADGE_KEY[data.status]}
            label={MERCHANT_STATUS_LABEL[data.status]}
          />
        </View>
        <Text style={[styles.submittedAt, { color: colors.textSecondary }]}>
          提交于 {data.submittedAt || '—'} · 申请编号 {data.id}
        </Text>
        {data.status === 'rejected' && data.rejectReason && (
          <View style={[styles.rejectBox, { backgroundColor: colors.errorBg }]}>
            <Text style={[styles.rejectText, { color: colors.error }]}>
              驳回原因：{data.rejectReason}
            </Text>
          </View>
        )}
      </View>

      <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>申请信息</Text>
      <View style={[styles.card, { backgroundColor: colors.cardBg }]}>
        {FIELD_ROWS.map((row) => (
          <View key={row.key} style={styles.fieldRow}>
            <Text style={[styles.fieldLabel, { color: colors.textSecondary }]}>{row.label}</Text>
            <Text style={[styles.fieldValue, { color: colors.textPrimary }]}>
              {String(data.form[row.key] || '—')}
            </Text>
          </View>
        ))}
      </View>

      <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>证照材料</Text>
      <View style={[styles.card, { backgroundColor: colors.cardBg }]}>
        {PHOTO_SLOTS.map((slot) => {
          const uri = data.form.photos[slot.key];
          return (
            <View key={slot.key} style={styles.fieldRow}>
              <Text style={[styles.fieldLabel, { color: colors.textSecondary }]}>{slot.label}</Text>
              <Text
                style={[
                  styles.fieldValue,
                  { color: uri ? colors.success : colors.error },
                ]}
                numberOfLines={1}
              >
                {uri ? '已上传 ✓' : '缺失 ✗'}
              </Text>
            </View>
          );
        })}
      </View>

      {auditable && (
        <>
          <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>审核操作</Text>
          <View style={[styles.card, { backgroundColor: colors.cardBg }]}>
            <TextInput
              testID="audit-reject-reason"
              accessibilityLabel="驳回原因"
              placeholder="驳回原因（驳回时必填，运营商可见）"
              placeholderTextColor={colors.textSecondary}
              value={rejectReason}
              onChangeText={setRejectReason}
              style={[
                styles.reasonInput,
                {
                  color: colors.textPrimary,
                  borderColor: colors.border,
                  backgroundColor: colors.pageBg,
                },
              ]}
              multiline
            />
            {actionError && (
              <Text style={[styles.actionError, { color: colors.error }]}>{actionError}</Text>
            )}
            <View style={styles.actionRow}>
              <TouchableOpacity
                testID="audit-reject-btn"
                accessibilityRole="button"
                style={[styles.actionBtn, styles.rejectBtn, { borderColor: colors.error }]}
                onPress={handleReject}
                disabled={submitting}
              >
                <Text style={[styles.actionBtnText, { color: colors.error }]}>驳回</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="audit-approve-btn"
                accessibilityRole="button"
                style={[styles.actionBtn, styles.approveBtn, { backgroundColor: colors.primary }]}
                onPress={confirmApprove}
                disabled={submitting}
              >
                <Text style={[styles.actionBtnText, { color: colors.onPrimary }]}>
                  {submitting ? '提交中...' : '批准进件'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </>
      )}

      {!auditable && (
        <Text style={[styles.doneHint, { color: colors.textSecondary }]}>
          {data.status === 'approved'
            ? '该申请已通过审核，无需操作'
            : '该申请已驳回，等待运营商修改后重新提交'}
        </Text>
      )}
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    padding: 12,
    gap: 10,
    paddingBottom: 32,
  },
  card: {
    borderRadius: 8,
    padding: 12,
    elevation: 1,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  companyName: {
    flex: 1,
    fontSize: 16,
    fontWeight: '600',
  },
  submittedAt: {
    marginTop: 6,
    fontSize: 12,
  },
  rejectBox: {
    marginTop: 10,
    borderRadius: 6,
    padding: 10,
  },
  rejectText: {
    fontSize: 13,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginTop: 4,
  },
  fieldRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    gap: 12,
  },
  fieldLabel: {
    fontSize: 13,
    flexShrink: 0,
  },
  fieldValue: {
    fontSize: 13,
    fontWeight: '500',
    textAlign: 'right',
    flexShrink: 1,
  },
  reasonInput: {
    borderWidth: 1,
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingTop: 8,
    paddingBottom: 8,
    minHeight: 64,
    fontSize: 13,
    textAlignVertical: 'top',
  },
  actionError: {
    marginTop: 8,
    fontSize: 12,
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 12,
  },
  actionBtn: {
    flex: 1,
    borderRadius: 6,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rejectBtn: {
    borderWidth: 1,
  },
  approveBtn: {
    // 背景运行时注入
  },
  actionBtnText: {
    fontSize: 14,
    fontWeight: '600',
  },
  doneHint: {
    textAlign: 'center',
    fontSize: 13,
    marginTop: 8,
  },
});

export default MerchantAuditDetailScreen;
