import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

type StatusType =
  | 'online'
  | 'offline'
  | 'fault'
  | 'maintenance'
  | 'warning'
  | 'critical'
  | 'info'
  | 'unhandled'
  | 'processing'
  | 'resolved'
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'cancelled'
  | 'high'
  | 'normal'
  | 'low'
  | 'urgent'
  | 'overdue';

interface StatusBadgeProps {
  status: StatusType;
  label?: string;
}

const STATUS_CONFIG: Record<string, { bg: string; text: string; label: string }> = {
  online:      { bg: '#e8f5e9', text: '#2e7d32', label: '在线' },
  offline:     { bg: '#fce4ec', text: '#c62828', label: '离线' },
  fault:       { bg: '#fff3e0', text: '#e65100', label: '故障' },
  maintenance: { bg: '#fff8e1', text: '#f57f17', label: '维护' },
  warning:     { bg: '#fff3e0', text: '#e65100', label: '警告' },
  critical:    { bg: '#fce4ec', text: '#c62828', label: '严重' },
  info:        { bg: '#e3f2fd', text: '#1565c0', label: '信息' },
  unhandled:   { bg: '#fce4ec', text: '#c62828', label: '未处理' },
  processing:  { bg: '#fff8e1', text: '#f57f17', label: '处理中' },
  resolved:    { bg: '#e8f5e9', text: '#2e7d32', label: '已解决' },
  pending:     { bg: '#fff8e1', text: '#f57f17', label: '待处理' },
  in_progress: { bg: '#e3f2fd', text: '#1565c0', label: '进行中' },
  completed:   { bg: '#e8f5e9', text: '#2e7d32', label: '已完成' },
  cancelled:   { bg: '#f5f5f5', text: '#616161', label: '已取消' },
  high:        { bg: '#fce4ec', text: '#c62828', label: '高' },
  normal:      { bg: '#e3f2fd', text: '#1565c0', label: '中' },
  low:         { bg: '#e8f5e9', text: '#2e7d32', label: '低' },
  urgent:      { bg: '#ffebee', text: '#b71c1c', label: '紧急' },
  overdue:     { bg: '#fce4ec', text: '#b71c1c', label: '已逾期' },
};

const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label }) => {
  const config = STATUS_CONFIG[status] || { bg: '#f5f5f5', text: '#616161', label: status };
  const displayLabel = label || config.label;

  return (
    <View style={[styles.badge, { backgroundColor: config.bg }]}>
      <Text style={[styles.text, { color: config.text }]}>{displayLabel}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 4,
    alignSelf: 'flex-start',
  },
  text: {
    fontSize: 12,
    fontWeight: '500',
  },
});

export default StatusBadge;