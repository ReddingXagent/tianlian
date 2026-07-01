import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
} from 'react-native';
import { couponApi } from '../services/api';
import { Coupon } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';
import StatusBadge from '../components/StatusBadge';

const CouponScreen: React.FC = () => {
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadCoupons = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await couponApi.getList();
      setCoupons(response.data.items);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '获取优惠券失败';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCoupons();
  }, []);

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

  if (loading) {
    return <LoadingSpinner text="加载优惠券..." />;
  }

  if (error) {
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
});

export default CouponScreen;