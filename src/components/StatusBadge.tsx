import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

type StatusType =
  | 'online'
  | 'offline'
  | 'fault'
  | 'maintenance'
  | 'idle'
  | 'charging'
  | 'completed'
  | 'cancelled'
  | 'unpaid'
  | 'paid'
  | 'unused'
  | 'used'
  | 'expired'
  | 'dc'
  | 'ac'
  | 'timeout';

interface StatusBadgeProps {
  status: StatusType;
  label?: string;
}

const STATUS_CONFIG: Record<string, { bg: string; text: string; label: string }> = {
  online:      { bg: '#e8f5e9', text: '#2e7d32', label: '在线' },
  offline:     { bg: '#fce4ec', text: '#c62828', label: '离线' },
  fault:       { bg: '#fff3e0', text: '#e65100', label: '故障' },
  maintenance: { bg: '#fff8e1', text: '#f57f17', label: '维护' },
  idle:        { bg: '#e8f5e9', text: '#2e7d32', label: '空闲' },
  charging:    { bg: '#e3f2fd', text: '#1565c0', label: '充电中' },
  completed:   { bg: '#e8f5e9', text: '#2e7d32', label: '已完成' },
  cancelled:   { bg: '#f5f5f5', text: '#616161', label: '已取消' },
  timeout:     { bg: '#fff3e0', text: '#e65100', label: '超时' },
  unpaid:      { bg: '#fff3e0', text: '#e65100', label: '未支付' },
  paid:        { bg: '#e8f5e9', text: '#2e7d32', label: '已支付' },
  unused:      { bg: '#e3f2fd', text: '#1565c0', label: '未使用' },
  used:        { bg: '#f5f5f5', text: '#616161', label: '已使用' },
  expired:     { bg: '#fce4ec', text: '#c62828', label: '已过期' },
  dc:          { bg: '#e3f2fd', text: '#1565c0', label: '直流' },
  ac:          { bg: '#f3e5f5', text: '#7b1fa2', label: '交流' },
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