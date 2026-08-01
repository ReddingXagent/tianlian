import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { WorkOrder } from '../types';
import StatusBadge from './StatusBadge';

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
  const content = (
    <View style={[styles.card, compact && styles.cardCompact]}>
      <View style={styles.header}>
        <Text style={styles.title} numberOfLines={1}>
          {order.title}
        </Text>
        <StatusBadge status={order.priority} />
      </View>
      {!compact && (
        <Text style={styles.desc} numberOfLines={2}>
          {order.description || '暂无描述'}
        </Text>
      )}
      <View style={styles.meta}>
        <Text style={styles.metaText}>
          {WORK_ORDER_TYPE_LABEL[order.type] || order.type}
        </Text>
        <Text style={styles.metaDot}>·</Text>
        <Text style={styles.metaText}>{order.stationName}</Text>
        <Text style={styles.metaDot}>·</Text>
        <Text style={styles.metaText}>
          {order.assigneeName || '未分配'}
        </Text>
      </View>
      <View style={styles.footer}>
        <StatusBadge status={order.status} />
        <Text style={styles.time}>
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
      >
        {content}
      </TouchableOpacity>
    );
  }

  return content;
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#fff',
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
    color: '#333',
    flex: 1,
    marginRight: 8,
  },
  desc: {
    fontSize: 13,
    color: '#666',
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
    color: '#999',
  },
  metaDot: {
    fontSize: 12,
    color: '#ccc',
    marginHorizontal: 4,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
  },
  time: {
    fontSize: 12,
    color: '#bbb',
  },
});

export default WorkOrderCard;
