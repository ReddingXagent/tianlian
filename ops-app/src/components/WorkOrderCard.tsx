import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { WorkOrder } from '../types';
import StatusBadge from './StatusBadge';
import { useTheme } from '../hooks/useTheme';

interface WorkOrderCardProps {
  order: WorkOrder;
  onPress?: (order: WorkOrder) => void;
  compact?: boolean;
}

const WORK_ORDER_TYPE_LABEL: Record<string, string> = {
  repair: '维修',
  inspection: '巡检',
  installation: '安装',
  maintenance: '保养',
  other: '其他',
};

const WorkOrderCard: React.FC<WorkOrderCardProps> = ({
  order,
  onPress,
  compact = false,
}) => {
  const { colors } = useTheme();
  const content = (
    <View style={[styles.card, { backgroundColor: colors.cardBg }, compact && styles.cardCompact]}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: colors.textPrimary }]} numberOfLines={1}>
          {order.title}
        </Text>
        <StatusBadge status={order.priority} />
      </View>
      {!compact && (
        <Text style={[styles.desc, { color: colors.textSecondary }]} numberOfLines={2}>
          {order.description || '暂无描述'}
        </Text>
      )}
      <View style={styles.meta}>
        <Text style={[styles.metaText, { color: colors.textSecondary }]}>
          {WORK_ORDER_TYPE_LABEL[order.type] || order.type}
        </Text>
        <Text style={[styles.metaDot, { color: colors.textMuted }]}>·</Text>
        <Text style={[styles.metaText, { color: colors.textSecondary }]}>{order.stationName}</Text>
        <Text style={[styles.metaDot, { color: colors.textMuted }]}>·</Text>
        <Text style={[styles.metaText, { color: colors.textSecondary }]}>
          {order.assigneeName || '未分配'}
        </Text>
      </View>
      <View style={[styles.footer, { borderTopColor: colors.divider }]}>
        <StatusBadge status={order.status} />
        <Text style={[styles.time, { color: colors.textMuted }]}>
          {new Date(order.createdAt).toLocaleDateString('zh-CN')}
        </Text>
      </View>
    </View>
  );

  if (onPress) {
    return (
      <TouchableOpacity
        onPress={() => onPress(order)}
        activeOpacity={0.7}
       accessibilityRole="button">
        {content}
      </TouchableOpacity>
    );
  }

  return content;
};

const styles = StyleSheet.create({
  card: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  cardCompact: {
    padding: 12,
    marginBottom: 8,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
    flex: 1,
    marginRight: 8,
  },
  desc: {
    fontSize: 13,
    lineHeight: 18,
    marginBottom: 8,
  },
  meta: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
    flexWrap: 'wrap',
  },
  metaText: {
    fontSize: 12,
  },
  metaDot: {
    fontSize: 12,
    marginHorizontal: 4,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    borderTopWidth: 1,
  },
  time: {
    fontSize: 12,
  },
});

export default WorkOrderCard;
