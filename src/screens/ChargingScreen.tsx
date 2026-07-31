import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { useRoute, RouteProp, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useOrderStore } from '../store/orderStore';
import { chargingApi } from '../services/api';
import { ChargingStatus, RootStackParamList } from '../types';

type ChargingRouteProp = RouteProp<RootStackParamList, 'Charging'>;
type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const ChargingScreen: React.FC = () => {
  const route = useRoute<ChargingRouteProp>();
  const navigation = useNavigation<NavigationProp>();
  const { orderId } = route.params;
  const [status, setStatus] = useState<ChargingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [stopping, setStopping] = useState(false);
  const stopCharging = useOrderStore((s) => s.stopCharging);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const response = await chargingApi.getStatus(orderId);
      const data = response.data;
      setStatus(data);
      if (data.status !== 'charging') {
        if (intervalRef.current) clearInterval(intervalRef.current);
        // 充电完成，跳转到支付页
        navigation.replace('Payment', { orderId, amount: data.amount });
      }
    } catch {
      if (intervalRef.current) clearInterval(intervalRef.current);
    } finally {
      setLoading(false);
    }
  }, [orderId, navigation]);

  useEffect(() => {
    fetchStatus();
    intervalRef.current = setInterval(fetchStatus, 3000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const handleStop = () => {
    Alert.alert(
      '停止充电',
      '确定要停止当前充电吗？',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '停止',
          style: 'destructive',
          onPress: async () => {
            setStopping(true);
            try {
              await stopCharging(orderId);
              if (intervalRef.current) clearInterval(intervalRef.current);
              if (status) {
                navigation.replace('Payment', { orderId, amount: status.amount });
              }
            } catch {
              Alert.alert('操作失败', '停止充电失败，请重试');
            } finally {
              setStopping(false);
            }
          },
        },
      ]
    );
  };

  if (loading || !status) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#1a73e8" />
        <Text style={styles.loadingText}>获取充电状态...</Text>
      </View>
    );
  }

  const power = status.power.toFixed(1);
  const energy = status.energy.toFixed(2);
  const duration = status.duration;
  const amount = status.amount.toFixed(2);
  const minutes = Math.floor(duration);
  const seconds = Math.floor((duration - minutes) * 60);

  return (
    <View style={styles.container}>
      {/* 充电动画区域 */}
      <View style={styles.animationArea}>
        <View style={styles.powerCircle}>
          <Text style={styles.powerIcon}>⚡</Text>
        </View>
        <Text style={styles.powerValue}>{power}</Text>
        <Text style={styles.powerUnit}>kW</Text>
      </View>

      {/* 充电信息 */}
      <View style={styles.infoCard}>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>充电站点</Text>
          <Text style={styles.infoValue}>{status.stationName}</Text>
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>充电桩</Text>
          <Text style={styles.infoValue}>{status.chargerName}</Text>
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>已充电量</Text>
          <Text style={styles.infoValue}>{energy} kWh</Text>
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>已充时长</Text>
          <Text style={styles.infoValue}>
            {minutes}分{seconds}秒
          </Text>
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>当前电压</Text>
          <Text style={styles.infoValue}>{status.voltage.toFixed(1)} V</Text>
        </View>
        <View style={[styles.infoRow, { borderBottomWidth: 0 }]}>
          <Text style={styles.infoLabel}>当前电流</Text>
          <Text style={styles.infoValue}>{status.current.toFixed(1)} A</Text>
        </View>
      </View>

      {/* 费用 */}
      <View style={styles.amountCard}>
        <Text style={styles.amountLabel}>当前费用</Text>
        <Text style={styles.amountValue}>
          <Text style={styles.amountNum}>¥{amount}</Text>
        </Text>
      </View>

      {/* 停止按钮 */}
      <TouchableOpacity
        style={[styles.stopBtn, stopping && styles.stopBtnDisabled]}
        onPress={handleStop}
        disabled={stopping}
        activeOpacity={0.7}
      >
        {stopping ? (
          <ActivityIndicator color="#fff" size="small" />
        ) : (
          <Text style={styles.stopBtnText}>停止充电</Text>
        )}
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f6fa',
    padding: 16,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#fff',
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    color: '#666',
  },
  animationArea: {
    alignItems: 'center',
    paddingVertical: 24,
  },
  powerCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#e3f2fd',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
  },
  powerIcon: {
    fontSize: 36,
  },
  powerValue: {
    fontSize: 40,
    fontWeight: '700',
    color: '#1a73e8',
  },
  powerUnit: {
    fontSize: 14,
    color: '#999',
    marginTop: 2,
  },
  infoCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  infoLabel: {
    fontSize: 14,
    color: '#999',
  },
  infoValue: {
    fontSize: 14,
    color: '#333',
    fontWeight: '500',
  },
  amountCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 20,
    alignItems: 'center',
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  amountLabel: {
    fontSize: 14,
    color: '#999',
    marginBottom: 4,
  },
  amountValue: {
    fontSize: 16,
    color: '#333',
  },
  amountNum: {
    fontSize: 32,
    fontWeight: '700',
    color: '#e65100',
  },
  stopBtn: {
    backgroundColor: '#c62828',
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
  },
  stopBtnDisabled: {
    opacity: 0.6,
  },
  stopBtnText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
  },
});

export default ChargingScreen;