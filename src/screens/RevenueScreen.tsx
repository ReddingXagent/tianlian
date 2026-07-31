import React, { useEffect, useState, useCallback } from 'react';
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
import { revenueApi } from '../services/api';
import { RevenueRecord } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';
import { buildRevenueCsv, revenueCsvFilename } from '../utils/csvExport';

type PeriodType = 'day' | 'week' | 'month';

const PERIOD_LABELS: Record<PeriodType, string> = {
  day: '日',
  week: '周',
  month: '月',
};

const screenWidth = Dimensions.get('window').width;

const RevenueScreen: React.FC = () => {
  const [period, setPeriod] = useState<PeriodType>('week');
  const [records, setRecords] = useState<RevenueRecord[]>([]);
  const [summary, setSummary] = useState({ today: 0, week: 0, month: 0, total: 0 });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      const [recordsRes, summaryRes] = await Promise.all([
        revenueApi.getRecords({ type: period }),
        revenueApi.getSummary(),
      ]);
      setRecords(recordsRes.data);
      setSummary(summaryRes.data);
    } catch {
      // 静默处理
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [period]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // 图表入场动画：每次数据加载完成淡入 + 上移
  // useState 惰性初始化替代 useRef().current: 渲染期读 ref 违反 react-hooks/refs
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

  // 导出 CSV：生成内容后调用系统分享面板
  const handleExport = useCallback(async () => {
    if (records.length === 0) return;
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
      ? records.map((r) => {
          const d = new Date(r.date);
          return `${d.getMonth() + 1}/${d.getDate()}`;
        })
      : ['暂无'],
    datasets: [
      {
        data: records.length > 0
          ? records.map((r) => r.amount)
          : [0],
        color: () => '#1a73e8',
        strokeWidth: 2,
      },
    ],
  };

  const totalAmount = records.reduce((sum, r) => sum + r.amount, 0);

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => fetchData(true)}
          colors={['#1a73e8']}
          tintColor="#1a73e8"
        />
      }
    >
      {/* 周期切换 */}
      <View style={styles.periodContainer}>
        {(Object.keys(PERIOD_LABELS) as PeriodType[]).map((p) => (
          <TouchableOpacity
            key={p}
            style={[styles.periodBtn, period === p && styles.periodBtnActive]}
            onPress={() => setPeriod(p)}
          >
            <Text style={[styles.periodBtnText, period === p && styles.periodBtnTextActive]}>
              {PERIOD_LABELS[p]}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading && !refreshing ? (
        <LoadingSpinner text="加载营收数据..." />
      ) : (
        <>
          {/* 汇总数据 (独立于明细, 无明细也展示) */}
          <View style={styles.summaryGrid}>
            <View style={styles.summaryCard}>
              <Text style={styles.summaryLabel}>今日</Text>
              <Text style={styles.summaryAmount}>¥{summary.today.toFixed(2)}</Text>
            </View>
            <View style={styles.summaryCard}>
              <Text style={styles.summaryLabel}>本周</Text>
              <Text style={styles.summaryAmount}>¥{summary.week.toFixed(2)}</Text>
            </View>
            <View style={styles.summaryCard}>
              <Text style={styles.summaryLabel}>本月</Text>
              <Text style={styles.summaryAmount}>¥{summary.month.toFixed(2)}</Text>
            </View>
            <View style={styles.summaryCard}>
              <Text style={styles.summaryLabel}>累计</Text>
              <Text style={[styles.summaryAmount, { color: '#1a73e8' }]}>
                ¥{summary.total.toFixed(2)}
              </Text>
            </View>
          </View>

          {records.length === 0 ? (
            <EmptyState icon="💰" title="暂无营收明细" message="当前周期内没有营收记录" />
          ) : (
            <>
          {/* 图表 */}
          <View style={styles.chartContainer}>
            <View style={styles.chartHeader}>
              <Text style={styles.chartTitle}>
                {PERIOD_LABELS[period]}营收趋势
              </Text>
              <TouchableOpacity style={styles.exportBtn} onPress={handleExport} activeOpacity={0.7}>
                <Text style={styles.exportBtnText}>📥 导出CSV</Text>
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
                    backgroundColor: '#fff',
                    backgroundGradientFrom: '#fff',
                    backgroundGradientTo: '#fff',
                    decimalPlaces: 0,
                    color: (opacity = 1) => `rgba(26, 115, 232, ${opacity})`,
                    labelColor: () => '#999',
                    propsForDots: {
                      r: '4',
                      strokeWidth: '2',
                      stroke: '#1a73e8',
                    },
                    propsForBackgroundLines: {
                      strokeDasharray: '',
                      stroke: '#f0f0f0',
                    },
                  }}
                  bezier
                  style={styles.chart}
                />
              </Animated.View>
            )}
          </View>

          {/* 数据明细 */}
          <Text style={styles.sectionTitle}>数据明细</Text>
          <View style={styles.totalRow}>
            <Text style={styles.totalLabel}>周期总计</Text>
            <Text style={styles.totalAmount}>¥{totalAmount.toFixed(2)}</Text>
          </View>
          {records.map((record, index) => (
            <View key={index} style={styles.recordRow}>
              <Text style={styles.recordDate}>{record.date}</Text>
              <Text style={styles.recordAmount}>¥{record.amount.toFixed(2)}</Text>
              <Text style={styles.recordCount}>{record.orderCount}笔</Text>
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
    backgroundColor: '#f5f6fa',
  },
  content: {
    padding: 16,
    paddingBottom: 32,
  },
  periodContainer: {
    flexDirection: 'row',
    backgroundColor: '#fff',
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
  periodBtnActive: {
    backgroundColor: '#1a73e8',
  },
  periodBtnText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#666',
  },
  periodBtnTextActive: {
    color: '#fff',
  },
  summaryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginBottom: 16,
  },
  summaryCard: {
    backgroundColor: '#fff',
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
    color: '#999',
    marginBottom: 6,
  },
  summaryAmount: {
    fontSize: 20,
    fontWeight: '700',
    color: '#333',
  },
  chartContainer: {
    backgroundColor: '#fff',
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
    color: '#333',
  },
  exportBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#e3f2fd',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  exportBtnText: {
    fontSize: 13,
    color: '#1565c0',
    fontWeight: '600',
  },
  chart: {
    borderRadius: 8,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    marginBottom: 10,
  },
  totalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#e3f2fd',
    borderRadius: 10,
    padding: 14,
    marginBottom: 8,
  },
  totalLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: '#1565c0',
  },
  totalAmount: {
    fontSize: 16,
    fontWeight: '700',
    color: '#1565c0',
  },
  recordRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderRadius: 8,
    padding: 12,
    marginBottom: 6,
  },
  recordDate: {
    fontSize: 13,
    color: '#666',
    flex: 1,
  },
  recordAmount: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333',
    flex: 1,
    textAlign: 'center',
  },
  recordCount: {
    fontSize: 13,
    color: '#999',
    flex: 1,
    textAlign: 'right',
  },
});

export default RevenueScreen;