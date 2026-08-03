import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { useIsFocused } from '@react-navigation/native';
import { useAuthStore } from '../store/authStore';
import { authApi, walletApi } from '../services/api';
import { WalletRecord } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';

const RECORD_TYPE_LABELS: Record<string, string> = {
  recharge: '充值',
  consume: '消费',
  refund: '退款',
  withdraw: '提现',
};

const WalletScreen: React.FC = () => {
  const { user, setUser } = useAuthStore();
  const [records, setRecords] = useState<WalletRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [recharging, setRecharging] = useState(false);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      const response = await walletApi.getRecords();
      setRecords(response.data.items);
    } catch {
      // 静默处理
    } finally {
      setLoading(false);
    }
  }, []);

  // 余额显示取自authStore.user.balance: 充电扣费/他处充值后回钱包页会陈旧
  // (F170/F176同型收尾) → 回焦静默重拉流水 + 拉最新profile同步余额。
  const isFocused = useIsFocused();
  const refreshProfile = useCallback(async () => {
    try {
      const response = await authApi.getProfile();
      setUser(response.data);
    } catch {
      // 静默处理
    }
  }, [setUser]);

  useEffect(() => {
    if (isFocused) {
      loadRecords();
      refreshProfile();
    }
  }, [isFocused, loadRecords, refreshProfile]);

  const handleRecharge = () => {
    const amounts = [10, 50, 100, 200];
    Alert.alert(
      '充值',
      '选择充值金额',
      amounts.map((amount) => ({
        text: `¥${amount}`,
        onPress: async () => {
          setRecharging(true);
          try {
            await walletApi.recharge(amount);
            // 刷新用户信息获取新余额
            const { authApi } = await import('../services/api');
            const response = await authApi.getProfile();
            setUser(response.data);
            loadRecords();
            Alert.alert('充值成功', `已充值 ¥${amount}`);
          } catch {
            Alert.alert('充值失败', '请重试');
          } finally {
            setRecharging(false);
          }
        },
      })),
      { cancelable: true }
    );
  };

  const renderRecordItem = ({ item }: { item: WalletRecord }) => (
    <View style={styles.recordCard}>
      <View style={styles.recordLeft}>
        <Text style={styles.recordType}>
          {RECORD_TYPE_LABELS[item.type] || item.type}
        </Text>
        <Text style={styles.recordDesc} numberOfLines={1}>{item.description}</Text>
        <Text style={styles.recordTime}>
          {new Date(item.createdAt).toLocaleString('zh-CN')}
        </Text>
      </View>
      <View style={styles.recordRight}>
        <Text
          style={[
            styles.recordAmount,
            { color: item.type === 'consume' ? '#c62828' : '#2e7d32' },
          ]}
        >
          {item.type === 'consume' || item.type === 'withdraw' ? '-' : '+'}
          ¥{item.amount.toFixed(2)}
        </Text>
        <Text style={styles.recordBalance}>余额 ¥{item.balance.toFixed(2)}</Text>
      </View>
    </View>
  );

  return (
    <View style={styles.container}>
      {/* 余额卡片 */}
      <View style={styles.balanceCard}>
        <Text style={styles.balanceLabel}>账户余额</Text>
        <Text style={styles.balanceValue}>
          ¥{(user?.balance || 0).toFixed(2)}
        </Text>
        <TouchableOpacity
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
      {loading ? (
        <LoadingSpinner text="加载记录..." />
      ) : records.length === 0 ? (
        <EmptyState
          icon="💰"
          title="暂无记录"
          message="还没有交易记录"
        />
      ) : (
        <FlatList
          data={records}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderRecordItem}
          contentContainerStyle={styles.listContent}
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
  balanceCard: {
    backgroundColor: '#1a73e8',
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
    color: '#fff',
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
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    padding: 16,
    paddingBottom: 8,
  },
  listContent: {
    paddingHorizontal: 16,
    paddingBottom: 32,
  },
  recordCard: {
    backgroundColor: '#fff',
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
    color: '#333',
    marginBottom: 2,
  },
  recordDesc: {
    fontSize: 12,
    color: '#999',
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
});

export default WalletScreen;