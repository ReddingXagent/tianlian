import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Dimensions,
} from 'react-native';
import { LineChart } from 'react-native-chart-kit';
import { chargerApi } from '../services/api';
import { useTheme } from '../hooks/useTheme';
import { ThemeColors } from '../theme/colors';
import { ChargerTrend, ChargerTrendMetric, ChargerTrendPoint } from '../types';
import LoadingSpinner from './LoadingSpinner';
import EmptyState from './EmptyState';

const screenWidth = Dimensions.get('window').width;

// 四个指标配置：标签 / 单位 / 语义色键（深色模式: 值改语义键，运行时解析随主题翻转）
const METRIC_CONFIG: Record<ChargerTrendMetric, { label: string; unit: string; color: keyof ThemeColors }> = {
  power:   { label: '功率', unit: 'kW', color: 'primary' },
  voltage: { label: '电压', unit: 'V',  color: 'chartPurple' },
  current: { label: '电流', unit: 'A',  color: 'chartOrange' },
  soc:     { label: 'SOC', unit: '%',   color: 'success' },
};

const formatClock = (ts: string): string => {
  try {
    return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
};

interface ChargerTrendChartProps {
  deviceId: number;
  deviceName?: string;
}

// 将趋势点转为图表标签（最多展示 6 个时间点，避免拥挤）
// 导出供测试直接验证防御分支（空输入兜底）
export const buildLabels = (points: ChargerTrendPoint[]): string[] => {
  if (points.length === 0) return [];
  const step = Math.max(1, Math.ceil(points.length / 6));
  return points.map((p, i) => (i % step === 0 ? formatClock(p.timestamp) : ''));
};

const ChargerTrendChart: React.FC<ChargerTrendChartProps> = ({ deviceId, deviceName }) => {
  const { colors } = useTheme();
  const [trend, setTrend] = useState<ChargerTrend | null>(null);
  const [metric, setMetric] = useState<ChargerTrendMetric>('power');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTrend = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await chargerApi.getTrend(deviceId);
      setTrend(res.data);
    } catch {
      setError('加载趋势数据失败');
    } finally {
      setLoading(false);
    }
  }, [deviceId]);

  useEffect(() => {
    // F1203: 微任务解耦 effect 直调 async —— deviceId 变化链同步适用
    Promise.resolve().then(() => fetchTrend());
  }, [fetchTrend]);

  const points = trend?.points ?? [];
  const metricColor = (m: ChargerTrendMetric): string => colors[METRIC_CONFIG[m].color];
  const config = METRIC_CONFIG[metric];

  const chartData = {
    labels: points.length > 0 ? buildLabels(points) : ['暂无'],
    datasets: [
      {
        data: points.length > 0 ? points.map((p) => p[metric]) : [0],
        color: () => metricColor(metric),
        strokeWidth: 2,
      },
    ],
  };

  // 最新值摘要 (bounds-checked: length>0 guarantees last element)
  const latest = points.length > 0 ? points[points.length - 1]![metric] : null;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: colors.textSecondary }]}>实时趋势</Text>
        <TouchableOpacity onPress={fetchTrend} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }} accessibilityRole="button">
          <Text style={[styles.refresh, { color: colors.primary }]}>刷新</Text>
        </TouchableOpacity>
      </View>

      {/* 指标切换 */}
      <View style={[styles.metricTabs, { backgroundColor: colors.neutralBg }]}>
        {(Object.keys(METRIC_CONFIG) as ChargerTrendMetric[]).map((m) => {
          const active = m === metric;
          const cfg = METRIC_CONFIG[m];
          return (
            <TouchableOpacity
              key={m}
              style={[styles.metricTab, active && { backgroundColor: colors[METRIC_CONFIG[m].color] }]}
              onPress={() => setMetric(m)}
              activeOpacity={0.7}
             accessibilityRole="button">
              <Text style={[styles.metricTabText, { color: active ? colors.onPrimary : colors.textSecondary }]}>
                {cfg.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {/* 当前值 */}
      {latest !== null && (
        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>当前{config.label}</Text>
          <Text style={[styles.summaryValue, { color: metricColor(metric) }]}>
            {latest.toFixed(metric === 'soc' ? 0 : 1)}
            <Text style={styles.summaryUnit}> {config.unit}</Text>
          </Text>
        </View>
      )}

      {loading ? (
        <LoadingSpinner text="加载趋势数据..." size="small" />
      ) : error ? (
        <EmptyState
          icon="⚠️"
          title="加载失败"
          message={error}
          actionLabel="重试"
          onAction={fetchTrend}
        />
      ) : points.length === 0 ? (
        <EmptyState icon="📉" title="暂无趋势数据" message="该充电桩暂无历史曲线" />
      ) : (
        <LineChart
          data={chartData}
          width={screenWidth - 64}
          height={160}
          yAxisSuffix={config.unit === '%' ? '%' : ''}
          yAxisLabel=""
          chartConfig={{
            backgroundColor: colors.cardBg,
            backgroundGradientFrom: colors.cardBg,
            backgroundGradientTo: colors.cardBg,
            decimalPlaces: metric === 'soc' ? 0 : 1,
            color: (opacity = 1) => `rgba(${hexToRgb(metricColor(metric))}, ${opacity})`,
            labelColor: () => colors.textSecondary,
            propsForDots: { r: '3', strokeWidth: '2', stroke: metricColor(metric) },
            propsForBackgroundLines: { strokeDasharray: '', stroke: colors.divider },
          }}
          bezier
          style={styles.chart}
        />
      )}
    </View>
  );
};

// hex(#1a73e8) -> "26,115,232" 供 rgba 使用
// 导出供测试直接验证防御分支（零通道/非法hex的 || 0 兜底）
export const hexToRgb = (hex: string): string => {
  const clean = hex.replace('#', '');
  const r = parseInt(clean.substring(0, 2), 16) || 0;
  const g = parseInt(clean.substring(2, 4), 16) || 0;
  const b = parseInt(clean.substring(4, 6), 16) || 0;
  return `${r},${g},${b}`;
};

const styles = StyleSheet.create({
  container: {
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  title: {
    fontSize: 14,
    fontWeight: '600',
  },
  refresh: {
    fontSize: 13,
  },
  metricTabs: {
    flexDirection: 'row',
    borderRadius: 8,
    padding: 3,
    marginBottom: 8,
  },
  metricTab: {
    flex: 1,
    paddingVertical: 6,
    borderRadius: 6,
    alignItems: 'center',
  },
  metricTabText: {
    fontSize: 12,
    fontWeight: '500',
  },
  metricTabTextActive: {
    fontWeight: '700',
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginBottom: 6,
  },
  summaryLabel: {
    fontSize: 12,
  },
  summaryValue: {
    fontSize: 18,
    fontWeight: '700',
  },
  summaryUnit: {
    fontSize: 12,
    fontWeight: '400',
  },
  chart: {
    borderRadius: 8,
  },
});

export default ChargerTrendChart;
