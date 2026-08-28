import React, { useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { useCoupons } from '../hooks/useCoupons';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';
import StatusBadge from '../components/StatusBadge';
import { formatDate, formatMoney } from '../utils/format';
import { useTheme } from '../hooks/useTheme';
import type { ThemeColors } from '../theme/colors';

const CouponScreen: React.FC = () => {
  const { colors } = useTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);

  const {
    coupons,
    loading,
    refreshing,
    error,
    hasMore,
    loadingMore,
    loadCoupons,
    loadMoreCoupons,
    handleRefresh,
  } = useCoupons();

  const renderCouponItem = ({ item }: { item: import('../types').Coupon }) => (
    <View style={styles.couponCard}>
      <View style={styles.couponHeader}>
        <Text style={styles.couponTitle}>{item.title}</Text>
        <StatusBadge status={item.status} />
      </View>
      <Text style={styles.couponDesc}>{item.description}</Text>
      <View style={styles.couponMeta}>
        <Text style={styles.couponMetaItem}>类型: {item.type}</Text>
        <Text style={styles.couponMetaItem}>面值: ¥{formatMoney(item.value)}</Text>
        <Text style={styles.couponMetaItem}>
          有效期: {formatDate(item.startAt)} - {formatDate(item.expireAt)}
        </Text>
      </View>
    </View>
  );

  // 仅首屏(无数据)才切整屏spinner/错误页; 下拉重拉/刷新失败时保留已有列表不闪屏(F209模式)
  if (loading && coupons.length === 0) {
    return <LoadingSpinner text="加载优惠券..." />;
  }

  if (error && coupons.length === 0) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error}
        actionLabel="重试"
        onAction={loadCoupons}
      />
    );
  }

  return (
    <View style={styles.container}>
      {coupons.length === 0 ? (
        <EmptyState
          icon="🎫"
          title="暂无优惠券"
          message="当前没有可用优惠券"
        />
      ) : (
        <FlatList
          data={coupons}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderCouponItem}
          contentContainerStyle={styles.listContent}
          onEndReached={loadMoreCoupons}
          onEndReachedThreshold={0.3}
          ListFooterComponent={
            loadingMore ? (
              <ActivityIndicator color={colors.primary} style={styles.footer} />
            ) : !hasMore && coupons.length > 0 ? (
              <Text style={styles.footerText}>没有更多了</Text>
            ) : null
          }
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={handleRefresh}
              colors={[colors.primary]}
              tintColor={colors.primary}
            />
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
  listContent: {
    padding: 16,
    paddingBottom: 32,
  },
  couponCard: {
    backgroundColor: colors.cardBg,
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  couponHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  couponTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.textPrimary,
  },
  couponDesc: {
    fontSize: 13,
    color: colors.textSecondary,
    marginBottom: 12,
  },
  couponMeta: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  couponMetaItem: {
    fontSize: 11,
    color: colors.textSecondary,
    backgroundColor: colors.pageBg,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
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

export default CouponScreen;
