import React, { useState, useMemo } from 'react';
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
import { useChargingPolling } from '../hooks/useChargingPolling';
import { ChargingStatus, RootStackParamList } from '../types';
import { formatMoney, formatEnergy } from '../utils/format';
import { useTheme } from '../hooks/useTheme';
import type { ThemeColors } from '../theme/colors';

type ChargingRouteProp = RouteProp<RootStackParamList, 'Charging'>;
type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const ChargingScreen: React.FC = () => {
  const { colors } = useTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);

  const route = useRoute<ChargingRouteProp>();
  const navigation = useNavigation<NavigationProp>();
  const { orderId } = route.params;
  const [stopping, setStopping] = useState(false);
  const stopCharging = useOrderStore((s) => s.stopCharging);

  // 移动端质量基线: 此前本屏自起裸 setInterval(3s), 后台/离线不停轮询(费电耗流量),
  // 且单次请求失败即永久停轮询(页面数据冻结)。改用 useChargingPolling:
  // 后台/断网自动暂停, 回前台/复网立即补拉; 偶发失败不中断轮询, 可手动重试。
  const { status, loading, error, paused, refresh } = useChargingPolling({
    orderId,
    onComplete: (data: ChargingStatus) => {
      // 充电完成，跳转到支付页
      navigation.replace('Payment', { orderId, amount: data.amount });
    },
  });

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
              navigation.replace('Payment', { orderId, amount: status!.amount });
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
    // 首帧失败(或持续失败): 给错误提示+手动重试, 不再静默转圈
    if (!loading && error) {
      return (
        <View style={styles.centerContainer}>
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity accessibilityRole="button" testID="charging-retry-btn" style={styles.retryBtn} onPress={() => refresh()}>
            <Text style={styles.retryBtnText}>重试</Text>
          </TouchableOpacity>
        </View>
      );
    }
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={styles.loadingText}>获取充电状态...</Text>
      </View>
    );
  }

  const power = status.power.toFixed(1);
  const energy = formatEnergy(status.energy);
  const duration = status.duration;
  const amount = formatMoney(status.amount);
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

      {/* 状态提示: 后台/离线暂停中 或 最近一次刷新失败 */}
      {(paused || error) && (
        <View style={styles.statusHint}>
          <Text style={styles.statusHintText}>
            {paused ? '实时刷新已暂停（后台/离线），回到前台自动恢复' : `刷新失败: ${error}，3秒后自动重试`}
          </Text>
        </View>
      )}

      {/* 停止按钮 */}
      <TouchableOpacity accessibilityRole="button"
        testID="stop-charging-btn"
        style={[styles.stopBtn, stopping && styles.stopBtnDisabled]}
        onPress={handleStop}
        disabled={stopping}
        activeOpacity={0.7}
      >
        {stopping ? (
          <ActivityIndicator color={colors.onPrimary} size="small" />
        ) : (
          <Text style={styles.stopBtnText}>停止充电</Text>
        )}
      </TouchableOpacity>
    </View>
  );
};

const createStyles = (colors: ThemeColors) =>
  StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.pageBg,
    padding: 16,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.pageBg,
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    color: colors.textSecondary,
  },
  animationArea: {
    alignItems: 'center',
    paddingVertical: 24,
  },
  powerCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: colors.infoBg,
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
    color: colors.primary,
  },
  powerUnit: {
    fontSize: 14,
    color: colors.textSecondary,
    marginTop: 2,
  },
  infoCard: {
    backgroundColor: colors.cardBg,
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
    borderBottomColor: colors.divider,
  },
  infoLabel: {
    fontSize: 14,
    color: colors.textSecondary,
  },
  infoValue: {
    fontSize: 14,
    color: colors.textPrimary,
    fontWeight: '500',
  },
  amountCard: {
    backgroundColor: colors.cardBg,
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
    color: colors.textSecondary,
    marginBottom: 4,
  },
  amountValue: {
    fontSize: 16,
    color: colors.textPrimary,
  },
  amountNum: {
    fontSize: 32,
    fontWeight: '700',
    color: colors.warning,
  },
  stopBtn: {
    backgroundColor: colors.error,
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
  },
  stopBtnDisabled: {
    opacity: 0.6,
  },
  stopBtnText: {
    color: colors.onPrimary,
    fontSize: 18,
    fontWeight: '600',
  },
  errorText: {
    fontSize: 14,
    color: colors.error,
    marginBottom: 16,
    textAlign: 'center',
    paddingHorizontal: 24,
  },
  retryBtn: {
    backgroundColor: colors.primary,
    borderRadius: 8,
    paddingHorizontal: 32,
    paddingVertical: 10,
  },
  retryBtnText: {
    color: colors.onPrimary,
    fontSize: 15,
    fontWeight: '600',
  },
  statusHint: {
    backgroundColor: colors.warningAmberBg,
    borderRadius: 8,
    padding: 10,
    marginBottom: 12,
  },
  statusHintText: {
    fontSize: 12,
    color: colors.warningAmber,
    textAlign: 'center',
  },
});

export default ChargingScreen;