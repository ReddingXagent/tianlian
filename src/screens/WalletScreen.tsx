import React, { useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { useAuthStore } from '../store/authStore';
import { useWallet } from '../hooks/useWallet';
import { WalletRecord } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';
import { formatDateTime, formatMoney } from '../utils/format';
import { useTheme } from '../hooks/useTheme';
import type { ThemeColors } from '../theme/colors';

const RECORD_TYPE_LABELS: Record<string, string> = {
  recharge: '充值',
  consume: '消费',
  refund: '退款',
  withdraw: '提现',
};

const WalletScreen: React.FC = () => {
  const { colors } = useTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);

  const { user } = useAuthStore();
  const {
    records,
    loading,
    error,
    refreshing,
    recharging,
    loadingMore,
    hasMore,
    loadRecords,
    loadMoreRecords,
    handleRefresh,
    recharge,
  } = useWallet();

  const handleRecharge = useCallback(() => {
    const amounts = [10, 50, 100, 200];
    Alert.alert(
      '充值',
      '选择充值金额',
      amounts.map((amount) => ({
        text: `¥${amount}`,
        onPress: async () => {
          const success = await recharge(amount);
          if (success) {
            Alert.alert('充值成功', `已充值 ¥${amount}`);
          } else {
            Alert.alert('充值失败', '请重试');
          }
        },
      })),
      { cancelable: true }
    );
  }, [recharge]);

  const renderRecordItem = ({ item }: { item: WalletRecord }) => (
    <View style={styles.recordCard}>
      <View style={styles.recordLeft}>
        <Text style={styles.recordType}>
          {RECORD_TYPE_LABELS[item.type] || item.type}
        </Text>
        <Text style={styles.recordDesc} numberOfLines={1}>{item.description}</Text>
        <Text style={styles.recordTime}>
          {formatDateTime(item.createdAt)}
        </Text>
      </View>
      <View style={styles.recordRight}>
        <Text
          style={[
            styles.recordAmount,
            { color: item.type === 'consume' ? colors.error : colors.success },
          ]}
        >
          {item.type === 'consume' || item.type === 'withdraw' ? '-' : '+'}
          ¥{formatMoney(item.amount)}
        </Text>
        <Text style={styles.recordBalance}>余额 ¥{formatMoney(item.balance)}</Text>
      </View>
    </View>
  );

  return (
    <View style={styles.container}>
      {/* 余额卡片 */}
      <View style={styles.balanceCard}>
        <Text style={styles.balanceLabel}>账户余额</Text>
        <Text style={styles.balanceValue}>
          ¥{formatMoney(user?.balance || 0)}
        </Text>
        <TouchableOpacity accessibilityRole="button"
          testID="wallet-recharge-btn"
          style={[styles.rechargeBtn, recharging && styles.rechargeBtnDisabled]}
          onPress={handleRecharge}
          disabled={recharging}
          activeOpacity={0.7}
        >
          <Text style={styles.rechargeBtnText}>
            {recharging ? '充值中...' : '充值'}
          </Text>
        </TouchableOpacity>
      </View>

      {/* 交易记录 */}
      <Text style={styles.sectionTitle}>交易记录</Text>
      {loading && records.length === 0 ? (
        <LoadingSpinner text="加载记录..." />
      ) : error && records.length === 0 ? (
        <EmptyState
          icon="⚠️"
          title="加载失败"
          message={error}
          actionLabel="重试"
          onAction={loadRecords}
        />
      ) : records.length === 0 ? (
        <EmptyState
          icon="💰"
          title="暂无记录"
          message="还没有交易记录"
        />
      ) : (
        <FlatList
          data={records}
          testID="wallet-record-list"
          keyExtractor={(item) => String(item.id)}
          renderItem={renderRecordItem}
          contentContainerStyle={styles.listContent}
          onEndReached={loadMoreRecords}
          onEndReachedThreshold={0.3}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={handleRefresh}
              colors={[colors.primary]}
              tintColor={colors.primary}
            />
          }
          ListFooterComponent={
            loadingMore ? (
              <ActivityIndicator color={colors.primary} style={styles.footer} />
            ) : !hasMore && records.length > 0 ? (
              <Text style={styles.footerText}>没有更多了</Text>
            ) : null
          }
        />
      )}
    </View>
  );
};

const createStyles = (colors: ThemeColors) =>
  StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.pageBg,
  },
  balanceCard: {
    backgroundColor: colors.primary,
    padding: 24,
    alignItems: 'center',
  },
  balanceLabel: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.8)',
    marginBottom: 8,
  },
  balanceValue: {
    fontSize: 40,
    fontWeight: '700',
    color: colors.onPrimary,
    marginBottom: 16,
  },
  rechargeBtn: {
    paddingHorizontal: 32,
    paddingVertical: 10,
    backgroundColor: 'rgba(255,255,255,0.2)',
    borderRadius: 20,
  },
  rechargeBtnDisabled: {
    opacity: 0.6,
  },
  rechargeBtnText: {
    color: colors.onPrimary,
    fontSize: 16,
    fontWeight: '600',
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.textPrimary,
    padding: 16,
    paddingBottom: 8,
  },
  listContent: {
    paddingHorizontal: 16,
    paddingBottom: 32,
  },
  recordCard: {
    backgroundColor: colors.cardBg,
    borderRadius: 10,
    padding: 14,
    marginBottom: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.03,
    shadowRadius: 3,
    elevation: 1,
  },
  recordLeft: {
    flex: 1,
  },
  recordType: {
    fontSize: 14,
    fontWeight: '500',
    color: colors.textPrimary,
    marginBottom: 2,
  },
  recordDesc: {
    fontSize: 12,
    color: colors.textSecondary,
    marginBottom: 2,
  },
  recordTime: {
    fontSize: 11,
    color: '#bbb',
  },
  recordRight: {
    alignItems: 'flex-end',
    justifyContent: 'center',
  },
  recordAmount: {
    fontSize: 16,
    fontWeight: '600',
  },
  recordBalance: {
    fontSize: 11,
    color: '#bbb',
    marginTop: 2,
  },
  footer: {
    marginVertical: 12,
  },
  footerText: {
    textAlign: 'center',
    fontSize: 12,
    color: '#bbb',
    marginVertical: 12,
  },
});

export default WalletScreen;
