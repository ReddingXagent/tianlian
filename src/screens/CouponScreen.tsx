import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { useIsFocused } from '@react-navigation/native';
import { couponApi } from '../services/api';
import { Coupon } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';
import StatusBadge from '../components/StatusBadge';

const PAGE_SIZE = 20;

const CouponScreen: React.FC = () => {
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 无限滚动分页状态(API本就分页, 此前UI只拉第一页)
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const loadCoupons = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await couponApi.getList({ page: 1, pageSize: PAGE_SIZE });
      setCoupons(response.data.items);
      setPage(response.data.page);
      setHasMore(response.data.items.length < response.data.total);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '获取优惠券失败';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMoreCoupons = useCallback(async () => {
    if (!hasMore || loadingMore || loading) return;
    setLoadingMore(true);
    try {
      const response = await couponApi.getList({ page: page + 1, pageSize: PAGE_SIZE });
      const data = response.data;
      const seen = new Set(coupons.map((c) => c.id));
      const merged = [...coupons, ...data.items.filter((c) => !seen.has(c.id))];
      setCoupons(merged);
      setPage(data.page);
      setHasMore(merged.length < data.total);
    } catch {
      // 静默处理, 下次触边可重试
    } finally {
      setLoadingMore(false);
    }
  }, [hasMore, loadingMore, loading, page, coupons]);

  // 回焦静默刷新: 支付/下单页用券后返回, 券状态(已用/过期)会陈旧。
  // 与订单/首页/钱包/站点详情等屏对齐(F170/F209交互一致性模式);
  // 重拉固定回第1页, 分页态随之重置。
  const isFocused = useIsFocused();

  useEffect(() => {
    if (isFocused) {
      loadCoupons();
    }
  }, [isFocused, loadCoupons]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadCoupons();
    setRefreshing(false);
  };

  const renderCouponItem = ({ item }: { item: Coupon }) => (
    <View style={styles.couponCard}>
      <View style={styles.couponHeader}>
        <Text style={styles.couponTitle}>{item.title}</Text>
        <StatusBadge status={item.status} />
      </View>
      <Text style={styles.couponDesc}>{item.description}</Text>
      <View style={styles.couponMeta}>
        <Text style={styles.couponMetaItem}>类型: {item.type}</Text>
        <Text style={styles.couponMetaItem}>面值: ¥{item.value.toFixed(2)}</Text>
        <Text style={styles.couponMetaItem}>
          有效期: {new Date(item.startAt).toLocaleDateString()} - {new Date(item.expireAt).toLocaleDateString()}
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
              <ActivityIndicator color="#1a73e8" style={styles.footer} />
            ) : !hasMore && coupons.length > 0 ? (
              <Text style={styles.footerText}>没有更多了</Text>
            ) : null
          }
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={handleRefresh}
              colors={["#1a73e8"]}
              tintColor="#1a73e8"
            />
          }
        />
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f6fa',
  },
  listContent: {
    padding: 16,
    paddingBottom: 32,
  },
  couponCard: {
    backgroundColor: '#fff',
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
    color: '#333',
  },
  couponDesc: {
    fontSize: 13,
    color: '#666',
    marginBottom: 12,
  },
  couponMeta: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  couponMetaItem: {
    fontSize: 11,
    color: '#999',
    backgroundColor: '#f5f6fa',
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