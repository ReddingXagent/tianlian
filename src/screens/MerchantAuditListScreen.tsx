/**
 * MerchantAuditListScreen.tsx — 商户进件审核列表 (卡 a8ca56aa ops-app 审核侧)
 * 运营商 (station-app) 提交的服务商特约商户进件申请在此审核;
 * 默认 mock 通道 (EXPO_PUBLIC_MERCHANT_KYC_MODE 未设), 契约落地后一键切 real.
 */
import { useCallback, useMemo, useState } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  StyleSheet,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { merchantAudit } from '../services/api-modules/merchant-audit-source';
import {
  MerchantApplication,
  MerchantApplicationStatus,
  MERCHANT_STATUS_LABEL,
  RootStackParamList,
} from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import { usePolling } from '../hooks/usePolling';
import { useTheme } from '../hooks/useTheme';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

/** 状态 → StatusBadge 语义色键 (pending/audit/rejected/approved 全部有预设) */
const STATUS_BADGE_KEY: Record<MerchantApplicationStatus, string> = {
  pending: 'pending',
  audit: 'processing',
  rejected: 'cancelled',
  approved: 'completed',
};

const FILTERS: { key: MerchantApplicationStatus | 'all'; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '待审核' },
  { key: 'audit', label: '审核中' },
  { key: 'rejected', label: '已驳回' },
  { key: 'approved', label: '已通过' },
];

/** mock uri 占位 → 摘要文本 (审核侧仅展示槽位在位状态, 真机 real 通道显示缩略图) */
function formatSubmittedAt(iso: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('zh-CN');
}

const MerchantAuditListScreen: React.FC = () => {
  const navigation = useNavigation<NavigationProp>();
  const { colors } = useTheme();
  const [filter, setFilter] = useState<MerchantApplicationStatus | 'all'>('all');

  const fetcher = useCallback(async () => {
    // 整页拉取后本地过滤 (mock 先行; 契约落地后映射层带 status 查询参数)
    const list = await merchantAudit.listApplications();
    return list;
  }, []);

  const { data, loading, error, refresh } = usePolling(fetcher, {
    interval: 15_000,
    enabled: true,
  });

  const applications = data?.items ?? null;
  const filtered = useMemo(() => {
    if (!applications) return [];
    return filter === 'all'
      ? applications
      : applications.filter((a) => a.status === filter);
  }, [applications, filter]);

  const refreshing = loading && applications !== null;

  const handlePress = (app: MerchantApplication) => {
    navigation.navigate('MerchantAuditDetail', { applicationId: app.id });
  };

  if (loading && !applications) {
    return <LoadingSpinner text="加载进件申请..." />;
  }

  if (error && !applications) {
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

  if (!applications || applications.length === 0) {
    return (
      <EmptyState
        icon="🏦"
        title="暂无进件申请"
        message="运营商提交商户进件后将显示在这里"
        actionLabel="刷新"
        onAction={refresh}
      />
    );
  }

  const pendingCount = applications.filter(
    (a) => a.status === 'pending' || a.status === 'audit'
  ).length;

  return (
    <View style={[styles.container, { backgroundColor: colors.pageBg }]}>
      <View style={styles.filterRow}>
        <Text style={[styles.pendingHint, { color: colors.textSecondary }]}>
          待处理 {pendingCount} 件
        </Text>
        {FILTERS.map((f) => {
          const active = filter === f.key;
          return (
            <TouchableOpacity
              key={f.key}
              testID={`audit-filter-${f.key}`}
              accessibilityRole="button"
              onPress={() => setFilter(f.key)}
              style={[
                styles.filterChip,
                { backgroundColor: active ? colors.primary : colors.cardBg },
              ]}
            >
              <Text
                style={[
                  styles.filterChipText,
                  { color: active ? colors.onPrimary : colors.textPrimary },
                ]}
              >
                {f.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
      <FlatList
        data={filtered}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={refresh}
            colors={[colors.primary]}
            tintColor={colors.primary}
          />
        }
        ListEmptyComponent={
          <EmptyState
            icon="🔍"
            title="该状态下无申请"
            message="切换其他状态筛选查看"
          />
        }
        renderItem={({ item }) => (
          <TouchableOpacity
            testID={`audit-item-${item.id}`}
            accessibilityRole="button"
            style={[styles.card, { backgroundColor: colors.cardBg }]}
            onPress={() => handlePress(item)}
          >
            <View style={styles.cardHeader}>
              <Text style={[styles.companyName, { color: colors.textPrimary }]} numberOfLines={1}>
                {item.form.companyName || `申请 #${item.id}`}
              </Text>
              <StatusBadge status={STATUS_BADGE_KEY[item.status]} label={MERCHANT_STATUS_LABEL[item.status]} />
            </View>
            <Text style={[styles.uscc, { color: colors.textSecondary }]} numberOfLines={1}>
              {item.form.uscc ? `统一社会信用代码 ${item.form.uscc}` : '信用代码缺失'}
            </Text>
            <View style={styles.cardFooter}>
              <Text style={[styles.meta, { color: colors.textSecondary }]}>
                {item.form.contactName} · {item.form.contactPhone || '无联系方式'}
              </Text>
              <Text style={[styles.meta, { color: colors.textSecondary }]}>
                {formatSubmittedAt(item.submittedAt)}
              </Text>
            </View>
          </TouchableOpacity>
        )}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  filterRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 6,
  },
  pendingHint: {
    fontSize: 12,
    marginRight: 4,
  },
  filterChip: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  filterChipText: {
    fontSize: 12,
    fontWeight: '500',
  },
  listContent: {
    padding: 12,
    gap: 10,
  },
  card: {
    borderRadius: 8,
    padding: 12,
    elevation: 1,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  companyName: {
    flex: 1,
    fontSize: 15,
    fontWeight: '600',
  },
  uscc: {
    marginTop: 4,
    fontSize: 12,
  },
  cardFooter: {
    marginTop: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
  },
  meta: {
    fontSize: 12,
    flexShrink: 1,
  },
});

export default MerchantAuditListScreen;
