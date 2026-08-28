import React, { useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
} from 'react-native';
import { useEnergy } from '../hooks/useEnergy';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';
import { formatEnergy, formatMoney } from '../utils/format';
import { useTheme } from '../hooks/useTheme';
import type { ThemeColors } from '../theme/colors';

const EnergyScreen: React.FC = () => {
  const { colors } = useTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);

  const { summary, loading, refreshing, error, refresh } = useEnergy();

  const handleRefresh = useCallback(() => {
    refresh();
  }, [refresh]);

  if (loading && !summary) {
    return <LoadingSpinner text="加载能源数据..." />;
  }

  if (error && !summary) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error}
        actionLabel="重试"
        onAction={() => refresh()}
      />
    );
  }

  if (!summary) {
    return (
      <EmptyState
        icon="📊"
        title="暂无数据"
        message="能源概览数据尚未生成"
        actionLabel="刷新"
        onAction={() => refresh()}
      />
    );
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={handleRefresh}
          colors={[colors.primary]}
          tintColor={colors.primary}
        />
      }
    >
      {/* 周期信息 */}
      <View style={styles.periodCard}>
        <Text style={styles.periodTitle}>统计周期</Text>
        <Text style={styles.periodValue}>{summary.period || '近30天'}</Text>
        <Text style={styles.periodDays}>{summary.days} 天</Text>
      </View>

      {/* 发电数据 */}
      <Text style={styles.sectionTitle}>发电</Text>
      <View style={styles.statsCard}>
        <StatRow
          label="光伏发电"
          value={`${formatEnergy(summary.pvGeneration)} kWh`}
        />
        <StatRow
          label="光伏收入"
          value={`¥${formatMoney(summary.pvRevenue)}`}
        />
        <StatRow
          label="同比"
          value={`${summary.yoy.pvGenerationYoY >= 0 ? '+' : '-'}${(Math.abs(summary.yoy.pvGenerationYoY) * 100).toFixed(1)}%`}
          valueColor={summary.yoy.pvGenerationYoY >= 0 ? colors.success : colors.error}
          isLast
        />
      </View>

      {/* 充电数据 */}
      <Text style={styles.sectionTitle}>充电</Text>
      <View style={styles.statsCard}>
        <StatRow
          label="充电量"
          value={`${formatEnergy(summary.chargingAmount)} kWh`}
        />
        <StatRow
          label="充电收入"
          value={`¥${formatMoney(summary.chargingRevenue)}`}
        />
        <StatRow
          label="同比"
          value={`${summary.yoy.chargingAmountYoY >= 0 ? '+' : '-'}${(Math.abs(summary.yoy.chargingAmountYoY) * 100).toFixed(1)}%`}
          valueColor={summary.yoy.chargingAmountYoY >= 0 ? colors.success : colors.error}
          isLast
        />
      </View>

      {/* 放电数据 */}
      <Text style={styles.sectionTitle}>放电</Text>
      <View style={styles.statsCard}>
        <StatRow
          label="放电量"
          value={`${formatEnergy(summary.dischargeAmount)} kWh`}
        />
        <StatRow
          label="放电收入"
          value={`¥${formatMoney(summary.dischargeRevenue)}`}
        />
        <StatRow
          label="同比"
          value={`${summary.yoy.dischargeAmountYoY >= 0 ? '+' : '-'}${(Math.abs(summary.yoy.dischargeAmountYoY) * 100).toFixed(1)}%`}
          valueColor={summary.yoy.dischargeAmountYoY >= 0 ? colors.success : colors.error}
          isLast
        />
      </View>

      {/* 总收入 */}
      <Text style={styles.sectionTitle}>总收入</Text>
      <View style={styles.totalCard}>
        <Text style={styles.totalValue}>¥{formatMoney(summary.totalRevenue)}</Text>
        <Text
          style={[
            styles.totalYoY,
            { color: summary.yoy.totalRevenueYoY >= 0 ? colors.success : colors.error },
          ]}
        >
          同比 {summary.yoy.totalRevenueYoY >= 0 ? '+' : '-'}{(Math.abs(summary.yoy.totalRevenueYoY) * 100).toFixed(1)}%
        </Text>
      </View>

      {/* 价格信息 */}
      <Text style={styles.sectionTitle}>当前电价</Text>
      <View style={styles.statsCard}>
        <StatRow
          label="上网电价"
          value={`¥${summary.priceInfo.feedInTariff.toFixed(2)}/kWh`}
        />
        <StatRow
          label="充电电价"
          value={`¥${summary.priceInfo.chargingPrice.toFixed(2)}/kWh`}
        />
        <StatRow
          label="放电电价"
          value={`¥${summary.priceInfo.dischargePrice.toFixed(2)}/kWh`}
          isLast
        />
      </View>
    </ScrollView>
  );
};

interface StatRowProps {
  label: string;
  value: string;
  valueColor?: string;
  isLast?: boolean;
}

// StatRow 的中性色随主题翻转(textPrimary/divider), 需注入主题色。
const StatRow: React.FC<StatRowProps> = ({ label, value, valueColor, isLast }) => {
  const { colors } = useTheme();
  return (
    <View
      style={{
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingHorizontal: 16,
        paddingVertical: 14,
        borderBottomWidth: isLast ? 0 : 1,
        borderBottomColor: colors.divider,
      }}
    >
      <Text style={{ fontSize: 15, color: colors.textPrimary }}>{label}</Text>
      <Text
        style={{
          fontSize: 15,
          fontWeight: '600',
          color: valueColor || colors.textPrimary,
        }}
      >
        {value}
      </Text>
    </View>
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
  periodCard: {
    backgroundColor: colors.primary,
    borderRadius: 16,
    padding: 20,
    alignItems: 'center',
    marginBottom: 16,
  },
  periodTitle: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.7)',
    marginBottom: 4,
  },
  periodValue: {
    fontSize: 20,
    fontWeight: '600',
    color: colors.onPrimary,
  },
  periodDays: {
    fontSize: 12,
    color: 'rgba(255,255,255,0.6)',
    marginTop: 4,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.textSecondary,
    marginBottom: 8,
    marginLeft: 4,
  },
  statsCard: {
    backgroundColor: colors.cardBg,
    borderRadius: 12,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  totalCard: {
    backgroundColor: colors.cardBg,
    borderRadius: 12,
    padding: 24,
    alignItems: 'center',
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  totalValue: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.primary,
  },
  totalYoY: {
    fontSize: 14,
    marginTop: 8,
  },
});

export default EnergyScreen;
