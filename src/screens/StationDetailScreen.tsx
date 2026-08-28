import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  Linking,
  Alert,
  Platform,
} from 'react-native';
import { useRoute, RouteProp, useNavigation, useIsFocused } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useStationStore } from '../store/stationStore';
import { RootStackParamList, Charger } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import { formatMoney } from '../utils/format';
import { useTheme } from '../hooks/useTheme';
import type { ThemeColors } from '../theme/colors';

type StationDetailRouteProp = RouteProp<RootStackParamList, 'StationDetail'>;
type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const StationDetailScreen: React.FC = () => {
  const { colors } = useTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);

  const route = useRoute<StationDetailRouteProp>();
  const navigation = useNavigation<NavigationProp>();
  const { stationId } = route.params;
  const {
    selectedStation,
    chargers,
    loading,
    error,
    fetchStationDetail,
    fetchChargers,
  } = useStationStore();
  const [refreshing, setRefreshing] = useState(false);

  const loadData = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    await Promise.all([
      fetchStationDetail(stationId),
      fetchChargers(stationId),
    ]);
    if (isRefresh) setRefreshing(false);
  }, [stationId, fetchStationDetail, fetchChargers]);

  // 移动端质量基线(F170/F176同型收尾): 详情页保活不重建,
  // 去充电/导航回来时桩位状态(空闲/占用/故障)可能已变 → 回焦静默重拉。
  const isFocused = useIsFocused();
  useEffect(() => {
    if (isFocused) {
      let cancelled = false;
      Promise.resolve().then(() => {
        if (!cancelled) loadData();
      });
      return () => { cancelled = true; };
    }
  }, [isFocused, loadData]);

  const handleNavigate = () => {
    if (!selectedStation) return;
    const { latitude, longitude, name } = selectedStation;
    const url = Platform.OS === 'ios'
      ? `maps://app?daddr=${latitude},${longitude}&q=${encodeURIComponent(name)}`
      : `geo:${latitude},${longitude}?q=${encodeURIComponent(name)}`;
    Linking.openURL(url).catch(() => {
      Alert.alert('提示', '无法打开地图应用');
    });
  };

  if (loading && !selectedStation) {
    return <LoadingSpinner text="加载站点详情..." />;
  }

  if (error && !selectedStation) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error}
        actionLabel="重试"
        onAction={() => loadData()}
      />
    );
  }

  const station = selectedStation;
  const availableCount = chargers.filter((c) => c.status === 'idle').length;
  const chargingCount = chargers.filter((c) => c.status === 'charging').length;

  const handleChargerPress = (charger: Charger) => {
    if (charger.status === 'idle') {
      // 导航到扫码页并传入充电桩信息
      Alert.alert(
        '开始充电',
        `是否使用 ${charger.name} 开始充电？`,
        [
          { text: '取消', style: 'cancel' },
          {
            text: '去充电',
            onPress: () => {
              // 跳转到扫码页，模拟已扫描
              navigation.navigate('Main', { screen: 'Scan' });
            },
          },
        ]
      );
    } else if (charger.status === 'charging') {
      Alert.alert('提示', '该充电桩正在使用中');
    } else if (charger.status === 'fault') {
      Alert.alert('提示', '该充电桩故障，请选择其他充电桩');
    } else {
      Alert.alert('提示', '该充电桩离线');
    }
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => loadData(true)}
          colors={[colors.primary]}
          tintColor={colors.primary}
        />
      }
    >
      {/* 站点信息卡片 */}
      <View style={styles.infoCard}>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>站点名称</Text>
          <Text style={styles.infoValue}>{station?.name}</Text>
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>状态</Text>
          <StatusBadge status={station?.status ?? 'offline'} />
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>地址</Text>
          <Text style={[styles.infoValue, styles.infoAddress]}>{station?.address}</Text>
        </View>
        <View style={[styles.infoRow, { borderBottomWidth: 0 }]}>
          <Text style={styles.infoLabel}>营业时间</Text>
          <Text style={styles.infoValue}>
            {station?.isOpen24h ? '24小时营业' : station?.openingHours || '-'}
          </Text>
        </View>
      </View>

      {/* 价格信息 */}
      <View style={styles.priceCard}>
        <Text style={styles.sectionTitle}>价格信息</Text>
        <View style={styles.priceRow}>
          <View style={styles.priceItem}>
            <Text style={styles.priceLabel}>电费</Text>
            <Text style={styles.priceValue}>
              <Text style={styles.priceNum}>{station && formatMoney(station.pricePerKwh)}</Text>
              <Text style={styles.priceUnit}> 元/度</Text>
            </Text>
          </View>
          <View style={styles.priceDivider} />
          <View style={styles.priceItem}>
            <Text style={styles.priceLabel}>服务费</Text>
            <Text style={styles.priceValue}>
              <Text style={styles.priceNum}>{station && formatMoney(station.serviceFee)}</Text>
              <Text style={styles.priceUnit}> 元/度</Text>
            </Text>
          </View>
          <View style={styles.priceDivider} />
          <View style={styles.priceItem}>
            <Text style={styles.priceLabel}>合计</Text>
            <Text style={styles.priceValue}>
              <Text style={[styles.priceNum, { color: colors.warning }]}>
                {formatMoney(station ? station.pricePerKwh + station.serviceFee : 0)}
              </Text>
              <Text style={styles.priceUnit}> 元/度</Text>
            </Text>
          </View>
        </View>
      </View>

      {/* 导航按钮 */}
      <TouchableOpacity accessibilityRole="button" style={styles.navButton} onPress={handleNavigate} activeOpacity={0.7}>
        <Text style={styles.navButtonIcon}>🗺️</Text>
        <Text style={styles.navButtonText}>导航到这里</Text>
      </TouchableOpacity>

      {/* 充电桩概览 */}
      <View style={styles.summaryRow}>
        <View style={styles.summaryItem}>
          <Text style={styles.summaryNum}>{chargers.length}</Text>
          <Text style={styles.summaryLabel}>总枪数</Text>
        </View>
        <View style={styles.summaryItem}>
          <Text style={[styles.summaryNum, { color: colors.success }]}>{availableCount}</Text>
          <Text style={styles.summaryLabel}>空闲</Text>
        </View>
        <View style={styles.summaryItem}>
          <Text style={[styles.summaryNum, { color: colors.info }]}>{chargingCount}</Text>
          <Text style={styles.summaryLabel}>充电中</Text>
        </View>
      </View>

      {/* 充电桩列表 */}
      <Text style={styles.sectionTitle}>充电桩列表</Text>
      {chargers.length === 0 ? (
        <EmptyState icon="🔌" title="暂无充电桩" message="该站点暂无充电桩" />
      ) : (
        chargers.map((charger) => (
          <TouchableOpacity accessibilityRole="button"
            key={charger.id}
            style={styles.chargerCard}
            onPress={() => handleChargerPress(charger)}
            activeOpacity={0.7}
          >
            <View style={styles.chargerHeader}>
              <Text style={styles.chargerName}>{charger.name}</Text>
              <StatusBadge status={charger.status} />
            </View>
            <View style={styles.chargerMeta}>
              <StatusBadge status={charger.type as 'dc' | 'ac'} />
              <Text style={styles.chargerPower}>{charger.power}kW</Text>
              <Text style={styles.chargerPrice}>
                {formatMoney(charger.pricePerKwh + charger.serviceFee)} 元/度
              </Text>
            </View>
          </TouchableOpacity>
        ))
      )}
    </ScrollView>
  );
};

const createStyles = (colors: ThemeColors) =>
  StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.pageBg,
  },
  content: {
    padding: 16,
    paddingBottom: 32,
  },
  infoCard: {
    backgroundColor: colors.cardBg,
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
    marginBottom: 12,
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
    flex: 1,
  },
  infoValue: {
    fontSize: 14,
    color: colors.textPrimary,
    fontWeight: '500',
    flex: 2,
    textAlign: 'right',
  },
  infoAddress: {
    fontSize: 13,
    color: colors.textSecondary,
  },
  priceCard: {
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
  sectionTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 10,
  },
  priceRow: {
    flexDirection: 'row',
    backgroundColor: colors.pageBg,
    borderRadius: 8,
    padding: 12,
  },
  priceItem: {
    flex: 1,
    alignItems: 'center',
  },
  priceLabel: {
    fontSize: 12,
    color: colors.textSecondary,
    marginBottom: 4,
  },
  priceValue: {
    fontSize: 13,
    color: colors.textPrimary,
  },
  priceNum: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.primary,
  },
  priceUnit: {
    fontSize: 12,
    color: colors.textSecondary,
  },
  priceDivider: {
    width: 1,
    backgroundColor: colors.border,
    marginHorizontal: 8,
  },
  navButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.cardBg,
    borderRadius: 12,
    padding: 14,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: colors.infoBg,
  },
  navButtonIcon: {
    fontSize: 18,
    marginRight: 8,
  },
  navButtonText: {
    fontSize: 15,
    color: colors.primary,
    fontWeight: '500',
  },
  summaryRow: {
    flexDirection: 'row',
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
  summaryItem: {
    flex: 1,
    alignItems: 'center',
  },
  summaryNum: {
    fontSize: 24,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  summaryLabel: {
    fontSize: 12,
    color: colors.textSecondary,
    marginTop: 2,
  },
  chargerCard: {
    backgroundColor: colors.cardBg,
    borderRadius: 10,
    padding: 14,
    marginBottom: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.03,
    shadowRadius: 3,
    elevation: 1,
  },
  chargerHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  chargerName: {
    fontSize: 15,
    fontWeight: '500',
    color: colors.textPrimary,
  },
  chargerMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  chargerPower: {
    fontSize: 13,
    color: colors.textSecondary,
    fontWeight: '500',
  },
  chargerPrice: {
    fontSize: 13,
    color: colors.warning,
    fontWeight: '500',
  },
});

export default StationDetailScreen;