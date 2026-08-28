import React, { useMemo } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { ThemeColors } from '../theme/colors';
import { useTheme } from '../hooks/useTheme';

export type StatusType =
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
  /** 已知状态有预设样式/文案；未知字符串原样展示（中性底） */
  status: StatusType | (string & {});
  label?: string;
}

/** 状态 → 语义色键映射（F2783 Phase 4b：值改语义键，运行时经 createStyles 解析，随主题翻转） */
type SemanticPair = { bg: keyof ThemeColors; text: keyof ThemeColors; label: string };

const STATUS_SEMANTICS: Record<string, SemanticPair> = {
  online:      { bg: 'successBg', text: 'success', label: '在线' },
  offline:     { bg: 'errorBg',   text: 'error',   label: '离线' },
  fault:       { bg: 'warningBg', text: 'warning', label: '故障' },
  maintenance: { bg: 'warningAmberBg', text: 'warningAmber', label: '维护' },
  idle:        { bg: 'successBg', text: 'success', label: '空闲' },
  charging:    { bg: 'infoBg',    text: 'info',    label: '充电中' },
  completed:   { bg: 'successBg', text: 'success', label: '已完成' },
  cancelled:   { bg: 'neutralBg', text: 'neutralText', label: '已取消' },
  timeout:     { bg: 'warningBg', text: 'warning', label: '超时' },
  unpaid:      { bg: 'warningBg', text: 'warning', label: '未支付' },
  paid:        { bg: 'successBg', text: 'success', label: '已支付' },
  unused:      { bg: 'infoBg',    text: 'info',    label: '未使用' },
  used:        { bg: 'neutralBg', text: 'neutralText', label: '已使用' },
  expired:     { bg: 'errorBg',   text: 'error',   label: '已过期' },
  dc:          { bg: 'infoBg',    text: 'info',    label: '直流' },
  ac:          { bg: 'purpleBg',  text: 'purple',  label: '交流' },
};

export const createStyles = (colors: ThemeColors) => {
  const resolve = (status: string): { bg: string; text: string; label: string } =>
    STATUS_SEMANTICS[status]
      ? { bg: colors[STATUS_SEMANTICS[status].bg], text: colors[STATUS_SEMANTICS[status].text], label: STATUS_SEMANTICS[status].label }
      : { bg: colors.neutralBg, text: colors.neutralText, label: status };

  return { resolve };
};

const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label }) => {
  const { colors } = useTheme();
  const { resolve } = useMemo(() => createStyles(colors), [colors]);
  const config = resolve(status);
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
