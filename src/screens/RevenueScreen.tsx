import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  Dimensions,
  Animated,
  Share,
  Alert,
} from 'react-native';
import { LineChart } from 'react-native-chart-kit';
import { useRevenue } from '../hooks/useRevenue';
import { RevenueRecord } from '../types';
import { useTheme } from '../hooks/useTheme';
import { hexToRgb } from '../components/ChargerTrendChart';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';
import { buildRevenueCsv } from '../utils/csvExport';

type PeriodType = 'day' | 'week' | 'month';

const PERIOD_LABELS: Record<PeriodType, string> = {
  day: '日',
  week: '周',
  month: '月',
};

const screenWidth = Dimensions.get('window').width;

const RevenueScreen: React.FC = () => {
  const { colors } = useTheme();
  const [period, setPeriod] = useState<PeriodType>('week');
  const { records, summary, loading, refreshing, fetchData } = useRevenue({ period });

  // 图表入场动画
  const [fadeAnim] = useState(() => new Animated.Value(0));
  useEffect(() => {
    if (records.length > 0 && !loading) {
      fadeAnim.setValue(0);
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 600,
        useNativeDriver: true,
      }).start();
    }
  }, [records, loading, fadeAnim]);

  // 导出 CSV
  const handleExport = useCallback(async () => {
    const csv = buildRevenueCsv(records, summary, period);
    try {
      await Share.share({
        message: csv,
        title: '天链V3 营收数据',
      });
    } catch {
      Alert.alert('导出失败', '无法导出数据，请稍后重试');
    }
  }, [records, summary, period]);

  const chartData = {
    labels: records.length > 0
      ? records.map((r: RevenueRecord) => {
          const d = new Date(r.date);
          return `${d.getMonth() + 1}/${d.getDate()}`;
        })
      : ['暂无'],
    datasets: [
      {
        data: records.length > 0
          ? records.map((r: RevenueRecord) => r.amount)
          : [0],
        color: () => colors.primary,
        strokeWidth: 2,
      },
    ],
  };

  const totalAmount = records.reduce((sum, r) => sum + r.amount, 0);

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.pageBg }]}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => fetchData(true)}
          colors={[colors.primary]}
          tintColor={colors.primary}
        />
      }
    >
      {/* 周期切换 */}
      <View style={[styles.periodContainer, { backgroundColor: colors.cardBg }]}>
        {(Object.keys(PERIOD_LABELS) as PeriodType[]).map((p) => (
          <TouchableOpacity
            key={p}
            style={[styles.periodBtn, period === p && { backgroundColor: colors.primary }]}
            onPress={() => setPeriod(p)}
           accessibilityRole="button">
            <Text
              style={[
                styles.periodBtnText,
                { color: colors.textSecondary },
                period === p && { color: colors.onPrimary },
              ]}
            >
              {PERIOD_LABELS[p]}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading && !refreshing ? (
        <LoadingSpinner text="加载营收数据..." />
      ) : (
        <>
          {/* 汇总数据 */}
          <View style={styles.summaryGrid}>
            <View style={[styles.summaryCard, { backgroundColor: colors.cardBg }]}>
              <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>今日</Text>
              <Text style={[styles.summaryAmount, { color: colors.textPrimary }]}>
                ¥{summary.today.toFixed(2)}
              </Text>
            </View>
            <View style={[styles.summaryCard, { backgroundColor: colors.cardBg }]}>
              <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>本周</Text>
              <Text style={[styles.summaryAmount, { color: colors.textPrimary }]}>
                ¥{summary.week.toFixed(2)}
              </Text>
            </View>
            <View style={[styles.summaryCard, { backgroundColor: colors.cardBg }]}>
              <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>本月</Text>
              <Text style={[styles.summaryAmount, { color: colors.textPrimary }]}>
                ¥{summary.month.toFixed(2)}
              </Text>
            </View>
            <View style={[styles.summaryCard, { backgroundColor: colors.cardBg }]}>
              <Text style={[styles.summaryLabel, { color: colors.textSecondary }]}>累计</Text>
              <Text style={[styles.summaryAmount, { color: colors.primary }]}>
                ¥{summary.total.toFixed(2)}
              </Text>
            </View>
          </View>

          {records.length === 0 ? (
            <EmptyState icon="💰" title="暂无营收明细" message="当前周期内没有营收记录" />
          ) : (
            <>
          {/* 图表 */}
          <View style={[styles.chartContainer, { backgroundColor: colors.cardBg }]}>
            <View style={styles.chartHeader}>
              <Text style={[styles.chartTitle, { color: colors.textPrimary }]}>
                {PERIOD_LABELS[period]}营收趋势
              </Text>
              <TouchableOpacity style={[styles.exportBtn, { backgroundColor: colors.infoBg }]} onPress={handleExport} activeOpacity={0.7} accessibilityRole="button">
                <Text style={[styles.exportBtnText, { color: colors.info }]}>📥 导出CSV</Text>
              </TouchableOpacity>
            </View>
            {records.length > 0 && (
              <Animated.View
                style={{
                  opacity: fadeAnim,
                  transform: [
                    {
                      translateY: fadeAnim.interpolate({
                        inputRange: [0, 1],
                        outputRange: [12, 0],
                      }),
                    },
                  ],
                }}
              >
                <LineChart
                  data={chartData}
                  width={screenWidth - 64}
                  height={220}
                  yAxisLabel="¥"
                  yAxisSuffix=""
                  chartConfig={{
                    backgroundColor: colors.cardBg,
                    backgroundGradientFrom: colors.cardBg,
                    backgroundGradientTo: colors.cardBg,
                    decimalPlaces: 0,
                    color: (opacity = 1) => `rgba(${hexToRgb(colors.primary)}, ${opacity})`,
                    labelColor: () => colors.textSecondary,
                    propsForDots: {
                      r: '4',
                      strokeWidth: '2',
                      stroke: colors.primary,
                    },
                    propsForBackgroundLines: {
                      strokeDasharray: '',
                      stroke: colors.divider,
                    },
                  }}
                  bezier
                  style={styles.chart}
                />
              </Animated.View>
            )}
          </View>

          {/* 数据明细 */}
          <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>数据明细</Text>
          <View style={[styles.totalRow, { backgroundColor: colors.infoBg }]}>
            <Text style={[styles.totalLabel, { color: colors.info }]}>周期总计</Text>
            <Text style={[styles.totalAmount, { color: colors.info }]}>¥{totalAmount.toFixed(2)}</Text>
          </View>
          {records.map((record, index) => (
            <View key={index} style={[styles.recordRow, { backgroundColor: colors.cardBg }]}>
              <Text style={[styles.recordDate, { color: colors.textSecondary }]}>{record.date}</Text>
              <Text style={[styles.recordAmount, { color: colors.textPrimary }]}>¥{record.amount.toFixed(2)}</Text>
              <Text style={[styles.recordCount, { color: colors.textSecondary }]}>{record.orderCount}笔</Text>
            </View>
          ))}
            </>
          )}
        </>
      )}
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    padding: 16,
    paddingBottom: 32,
  },
  periodContainer: {
    flexDirection: 'row',
    borderRadius: 10,
    padding: 4,
    marginBottom: 16,
  },
  periodBtn: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderRadius: 8,
  },
  periodBtnText: {
    fontSize: 14,
    fontWeight: '500',
  },
  summaryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginBottom: 16,
  },
  summaryCard: {
    borderRadius: 12,
    padding: 16,
    width: (screenWidth - 52) / 2,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  summaryLabel: {
    fontSize: 13,
    marginBottom: 6,
  },
  summaryAmount: {
    fontSize: 20,
    fontWeight: '700',
  },
  chartContainer: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  chartHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  chartTitle: {
    fontSize: 16,
    fontWeight: '600',
  },
  exportBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  exportBtnText: {
    fontSize: 13,
    fontWeight: '600',
  },
  chart: {
    borderRadius: 8,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 10,
  },
  totalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderRadius: 10,
    padding: 14,
    marginBottom: 8,
  },
  totalLabel: {
    fontSize: 14,
    fontWeight: '500',
  },
  totalAmount: {
    fontSize: 16,
    fontWeight: '700',
  },
  recordRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderRadius: 8,
    padding: 12,
    marginBottom: 6,
  },
  recordDate: {
    fontSize: 13,
    flex: 1,
  },
  recordAmount: {
    fontSize: 14,
    fontWeight: '600',
    flex: 1,
    textAlign: 'center',
  },
  recordCount: {
    fontSize: 13,
    flex: 1,
    textAlign: 'right',
  },
});

export default RevenueScreen;
