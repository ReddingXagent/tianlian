import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Station } from '../types';
import { formatDistance, formatMoney } from '../utils/format';
import StatusBadge from './StatusBadge';
import { useTheme } from '../hooks/useTheme';
import type { ThemeColors } from '../theme/colors';

interface StationCardProps {
  station: Station;
  onPress: (station: Station) => void;
}

const StationCard: React.FC<StationCardProps> = ({ station, onPress }) => {
  const { colors } = useTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);
  const distanceText = station.distance
    ? formatDistance(station.distance)
    : null;

  const availableText = `${station.availableConnectors}/${station.totalConnectors}`;
  const hasAvailable = station.availableConnectors > 0;

  return (
    <TouchableOpacity accessibilityRole="button"
      style={styles.card}
      onPress={() => onPress(station)}
      activeOpacity={0.7}
    >
      {/* 顶部：名称 + 状态 */}
      <View style={styles.topRow}>
        <Text style={styles.name} numberOfLines={1}>{station.name}</Text>
        <StatusBadge status={station.status} />
      </View>

      {/* 地址 */}
      <Text style={styles.address} numberOfLines={1}>{station.address}</Text>

      {/* 价格信息 */}
      <View style={styles.priceRow}>
        <View style={styles.priceItem}>
          <Text style={styles.priceLabel}>电费</Text>
          <Text style={styles.priceValue}>
            <Text style={[styles.priceNum, { color: colors.primary }]}>{formatMoney(station.pricePerKwh)}</Text>
            <Text style={styles.priceUnit}> 元/度</Text>
          </Text>
        </View>
        <View style={styles.priceDivider} />
        <View style={styles.priceItem}>
          <Text style={styles.priceLabel}>服务费</Text>
          <Text style={styles.priceValue}>
            <Text style={[styles.priceNum, { color: colors.primary }]}>{formatMoney(station.serviceFee)}</Text>
            <Text style={styles.priceUnit}> 元/度</Text>
          </Text>
        </View>
      </View>

      {/* 底部：距离 + 可用枪数 */}
      <View style={styles.bottomRow}>
        <View style={styles.availabilityRow}>
          <Text style={[styles.availabilityDot, { color: hasAvailable ? colors.success : colors.error }]}>
            ●
          </Text>
          <Text style={[styles.availabilityText, { color: hasAvailable ? colors.success : colors.error }]}>
            {hasAvailable ? `可用 ${availableText}` : `已满 ${availableText}`}
          </Text>
        </View>
        {distanceText && (
          <Text style={styles.distance}>{distanceText}</Text>
        )}
      </View>
    </TouchableOpacity>
  );
};

const createStyles = (colors: ThemeColors) =>
  StyleSheet.create({
  card: {
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
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  name: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.textPrimary,
    flex: 1,
    marginRight: 8,
  },
  address: {
    fontSize: 13,
    color: colors.textSecondary,
    marginBottom: 10,
  },
  priceRow: {
    flexDirection: 'row',
    backgroundColor: colors.pageBg,
    borderRadius: 8,
    padding: 10,
    marginBottom: 10,
  },
  priceItem: {
    flex: 1,
    alignItems: 'center',
  },
  priceLabel: {
    fontSize: 12,
    color: colors.textSecondary,
    marginBottom: 2,
  },
  priceValue: {
    fontSize: 13,
    color: colors.textPrimary,
  },
  priceNum: {
    fontSize: 18,
    fontWeight: '700',
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
  bottomRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  availabilityRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  availabilityDot: {
    fontSize: 10,
    marginRight: 4,
  },
  availabilityText: {
    fontSize: 13,
    fontWeight: '500',
  },
  distance: {
    fontSize: 13,
    color: colors.textSecondary,
  },
});

export default StationCard;