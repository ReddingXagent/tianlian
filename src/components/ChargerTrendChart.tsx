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
import { ChargerTrend, ChargerTrendMetric, ChargerTrendPoint } from '../types';
import LoadingSpinner from './LoadingSpinner';
import EmptyState from './EmptyState';

const screenWidth = Dimensions.get('window').width;

// 四个指标配置：标签 / 单位 / 主色
const METRIC_CONFIG: Record<ChargerTrendMetric, { label: string; unit: string; color: string }> = {
  power:   { label: '功率', unit: 'kW', color: '#1a73e8' },
  voltage: { label: '电压', unit: 'V',  color: '#7b1fa2' },
  current: { label: '电流', unit: 'A',  color: '#ef6c00' },
  soc:     { label: 'SOC', unit: '%',   color: '#2e7d32' },
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
  const config = METRIC_CONFIG[metric];

  const chartData = {
    labels: points.length > 0 ? buildLabels(points) : ['暂无'],
    datasets: [
      {
        data: points.length > 0 ? points.map((p) => p[metric]) : [0],
        color: () => config.color,
        strokeWidth: 2,
      },
    ],
  };

  // 最新值摘要
  const latest = points.length > 0 ? points[points.length - 1][metric] : null;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>实时趋势</Text>
        <TouchableOpacity onPress={fetchTrend} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
          <Text style={styles.refresh}>刷新</Text>
        </TouchableOpacity>
      </View>

      {/* 指标切换 */}
      <View style={styles.metricTabs}>
        {(Object.keys(METRIC_CONFIG) as ChargerTrendMetric[]).map((m) => {
          const active = m === metric;
          const cfg = METRIC_CONFIG[m];
          return (
            <TouchableOpacity
              key={m}
              style={[styles.metricTab, active && { backgroundColor: cfg.color }]}
              onPress={() => setMetric(m)}
              activeOpacity={0.7}
            >
              <Text style={[styles.metricTabText, active && styles.metricTabTextActive]}>
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
          <Text style={[styles.summaryValue, { color: config.color }]}>
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
            backgroundColor: '#fff',
            backgroundGradientFrom: '#fff',
            backgroundGradientTo: '#fff',
            decimalPlaces: metric === 'soc' ? 0 : 1,
            color: (opacity = 1) => `rgba(${hexToRgb(config.color)}, ${opacity})`,
            labelColor: () => '#999',
            propsForDots: { r: '3', strokeWidth: '2', stroke: config.color },
            propsForBackgroundLines: { strokeDasharray: '', stroke: '#f0f0f0' },
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
    borderTopColor: '#f0f0f0',
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
    color: '#555',
  },
  refresh: {
    fontSize: 13,
    color: '#1a73e8',
  },
  metricTabs: {
    flexDirection: 'row',
    backgroundColor: '#f0f2f5',
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
    color: '#666',
    fontWeight: '500',
  },
  metricTabTextActive: {
    color: '#fff',
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
    color: '#999',
  },
  summaryValue: {
    fontSize: 18,
    fontWeight: '700',
  },
  summaryUnit: {
    fontSize: 12,
    color: '#999',
    fontWeight: '400',
  },
  chart: {
    borderRadius: 8,
  },
});

export default ChargerTrendChart;
