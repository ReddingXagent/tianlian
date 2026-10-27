import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { useRoute, RouteProp } from '@react-navigation/native';
import { useDeviceDetail } from '../hooks/useDeviceDetail';
import { RootStackParamList, DeviceControlLog } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import { useTheme } from '../hooks/useTheme';
import ConfirmDialog from '../components/ConfirmDialog';
import { useDeviceControlLogStore } from '../store/deviceControlLogStore';

type DeviceDetailRouteProp = RouteProp<RootStackParamList, 'DeviceDetail'>;

const DEVICE_TYPE_LABEL: Record<string, string> = {
  charger: '充电桩',
  battery: '电池',
  inverter: '逆变器',
  sensor: '传感器',
  other: '其他',
};

const DeviceDetailScreen: React.FC = () => {
  const { colors } = useTheme();
  const route = useRoute<DeviceDetailRouteProp>();
  const { deviceId } = route.params;

  const { device, telemetry, loading, refreshing, error, controlling, fetchData, controlDevice } =
    useDeviceDetail({ deviceId });

  // 待确认的远程控制指令
  const [confirmCommand, setConfirmCommand] = useState<{
    command: string;
    label: string;
    danger: boolean;
  } | null>(null);

  // 操作日志（本地）
  const logs = useDeviceControlLogStore((s) => s.logs);
  const addLog = useDeviceControlLogStore((s) => s.addLog);
  const clearLogs = useDeviceControlLogStore((s) => s.clearLogs);
  const deviceLogs = logs.filter((l) => l.deviceId === deviceId);

  // 点击控制按钮 → 弹出确认对话框
  const handleControl = (command: string, label: string, danger = false) => {
    setConfirmCommand({ command, label, danger });
  };

  // 确认后真正下发指令，并写入操作日志
  const executeControl = async () => {
    const { command, label } = confirmCommand!;
    const result = await controlDevice(command);

    if (result.success) {
      const message = result.message || `${label}指令已发送`;
      addLog({
        deviceId,
        deviceName: device!.name,
        command: command as DeviceControlLog['command'],
        commandLabel: label,
        status: 'success',
        message,
        operator: '当前用户',
      });
      Alert.alert('操作成功', message);
    } else {
      const failMsg = `发送${label}指令失败`;
      addLog({
        deviceId,
        deviceName: device!.name,
        command: command as DeviceControlLog['command'],
        commandLabel: label,
        status: 'failed',
        message: failMsg,
        operator: '当前用户',
      });
      Alert.alert('操作失败', `${failMsg}，请稍后重试`);
    }
    setConfirmCommand(null);
  };

  const formatLogTime = (dateStr: string): string => {
    try {
      return new Date(dateStr).toLocaleString('zh-CN');
    } catch {
      return dateStr;
    }
  };

  if (loading && !device) {
    return <LoadingSpinner text="加载设备详情..." />;
  }

  if (error && !device) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error}
        actionLabel="重试"
        onAction={() => fetchData()}
      />
    );
  }

  return (
    <>
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
      {/* 设备基本信息 */}
      <View style={[styles.infoCard, { backgroundColor: colors.cardBg }]}>
        <View style={styles.infoHeader}>
          <Text style={styles.deviceIcon}>
            {device?.type === 'charger' ? '🔌' : device?.type === 'battery' ? '🔋' : device?.type === 'inverter' ? '⚡' : '📡'}
          </Text>
          <View style={styles.infoHeaderContent}>
            <Text style={[styles.deviceName, { color: colors.textPrimary }]}>{device?.name}</Text>
            <Text style={[styles.deviceCode, { color: colors.textSecondary }]}>编号: {device?.code}</Text>
          </View>
          <StatusBadge status={device?.status ?? 'offline'} />
        </View>

        <View style={[styles.infoDivider, { backgroundColor: colors.divider }]} />

        <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
          <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>类型</Text>
          <Text style={[styles.infoValue, { color: colors.textPrimary }]}>{DEVICE_TYPE_LABEL[device?.type ?? 'other']}</Text>
        </View>
        <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
          <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>型号</Text>
          <Text style={[styles.infoValue, { color: colors.textPrimary }]}>{device?.model || '-'}</Text>
        </View>
        <View style={[styles.infoRow, { borderBottomColor: colors.divider }]}>
          <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>厂商</Text>
          <Text style={[styles.infoValue, { color: colors.textPrimary }]}>{device?.manufacturer || '-'}</Text>
        </View>
        <View style={[styles.infoRow, { borderBottomWidth: 0, borderBottomColor: 'transparent' }]}>
          <Text style={[styles.infoLabel, { color: colors.textSecondary }]}>最后心跳</Text>
          <Text style={[styles.infoValue, { color: colors.textPrimary }]}>
            {device?.lastHeartbeat
              ? new Date(device.lastHeartbeat).toLocaleString('zh-CN')
              : '无数据'}
          </Text>
        </View>
      </View>

      {/* 遥测数据 */}
      {telemetry && (
        <View style={styles.section}>
          <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>实时遥测</Text>
          <View style={styles.telemetryGrid}>
            <View style={[styles.telemetryCard, { backgroundColor: colors.cardBg }]}>
              <Text style={[styles.telemetryValue, { color: colors.textPrimary }]}>{telemetry.power.toFixed(1)}</Text>
              <Text style={[styles.telemetryUnit, { color: colors.textSecondary }]}>kW</Text>
              <Text style={[styles.telemetryLabel, { color: colors.textMuted }]}>功率</Text>
            </View>
            <View style={[styles.telemetryCard, { backgroundColor: colors.cardBg }]}>
              <Text style={[styles.telemetryValue, { color: colors.textPrimary }]}>{telemetry.voltage.toFixed(0)}</Text>
              <Text style={[styles.telemetryUnit, { color: colors.textSecondary }]}>V</Text>
              <Text style={[styles.telemetryLabel, { color: colors.textMuted }]}>电压</Text>
            </View>
            <View style={[styles.telemetryCard, { backgroundColor: colors.cardBg }]}>
              <Text style={[styles.telemetryValue, { color: colors.textPrimary }]}>{telemetry.current.toFixed(1)}</Text>
              <Text style={[styles.telemetryUnit, { color: colors.textSecondary }]}>A</Text>
              <Text style={[styles.telemetryLabel, { color: colors.textMuted }]}>电流</Text>
            </View>
            <View style={[styles.telemetryCard, { backgroundColor: colors.cardBg }]}>
              <Text style={[styles.telemetryValue, {
                color: telemetry.temperature > 60 ? colors.error : telemetry.temperature > 45 ? colors.warningAmber : colors.textPrimary,
              }]}>
                {telemetry.temperature.toFixed(0)}
              </Text>
              <Text style={[styles.telemetryUnit, { color: colors.textSecondary }]}>°C</Text>
              <Text style={[styles.telemetryLabel, { color: colors.textMuted }]}>温度</Text>
            </View>
            <View style={[styles.telemetryCard, { backgroundColor: colors.cardBg }]}>
              <Text style={[styles.telemetryValue, { color: colors.textPrimary }]}>{telemetry.energy.toFixed(1)}</Text>
              <Text style={[styles.telemetryUnit, { color: colors.textSecondary }]}>kWh</Text>
              <Text style={[styles.telemetryLabel, { color: colors.textMuted }]}>累计电量</Text>
            </View>
          </View>
          <Text style={[styles.telemetryTime, { color: colors.textMuted }]}>
            更新时间: {new Date(telemetry.timestamp).toLocaleString('zh-CN')}
          </Text>
        </View>
      )}

      {/* 远程控制 */}
      <View style={styles.section}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>远程控制</Text>
        <View style={styles.controlGrid}>
          <TouchableOpacity
            style={[styles.controlBtn, { backgroundColor: colors.successBg }]}
            onPress={() => handleControl('start', '启动')}
            disabled={controlling || device?.status === 'online'}
            activeOpacity={0.7}
           accessibilityRole="button">
            {controlling ? (
              <ActivityIndicator color={colors.success} size="small" />
            ) : (
              <>
                <Text style={styles.controlIcon}>▶️</Text>
                <Text style={[styles.controlLabel, { color: colors.success }]}>启动</Text>
              </>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.controlBtn, { backgroundColor: colors.errorBg }]}
            onPress={() => handleControl('stop', '停止', true)}
            disabled={controlling}
            activeOpacity={0.7}
           accessibilityRole="button">
            <Text style={styles.controlIcon}>⏹️</Text>
            <Text style={[styles.controlLabel, { color: colors.error }]}>停止</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.controlBtn, { backgroundColor: colors.warningAmberBg }]}
            onPress={() => handleControl('restart', '重启')}
            disabled={controlling}
            activeOpacity={0.7}
           accessibilityRole="button">
            <Text style={styles.controlIcon}>🔄</Text>
            <Text style={[styles.controlLabel, { color: colors.warningAmber }]}>重启</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.controlBtn, { backgroundColor: colors.infoBg }]}
            onPress={() => handleControl('reset', '复位')}
            disabled={controlling}
            activeOpacity={0.7}
           accessibilityRole="button">
            <Text style={styles.controlIcon}>🔧</Text>
            <Text style={[styles.controlLabel, { color: colors.info }]}>复位</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* 操作日志 */}
      <View style={styles.section}>
        <View style={styles.logHeader}>
          <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>操作日志</Text>
          {deviceLogs.length > 0 && (
            <TouchableOpacity onPress={clearLogs} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }} accessibilityRole="button"
              testID="devicedetail-clear-logs-btn"
            >
              <Text style={[styles.clearLogText, { color: colors.error }]}>清空</Text>
            </TouchableOpacity>
          )}
        </View>
        {deviceLogs.length === 0 ? (
          <Text style={[styles.logEmpty, { color: colors.textMuted, backgroundColor: colors.cardBg }]}>暂无操作记录</Text>
        ) : (
          deviceLogs.map((log) => (
            <View
              key={log.id}
              style={[styles.logItem, { backgroundColor: colors.cardBg, borderLeftColor: log.status === 'failed' ? colors.error : colors.success }]}
            >
              <View style={styles.logRow}>
                <Text style={[styles.logCommand, { color: colors.textPrimary }]}>{log.commandLabel}</Text>
                <Text style={[styles.logStatus, { color: log.status === 'failed' ? colors.error : colors.success, backgroundColor: log.status === 'failed' ? colors.errorBg : colors.successBg }]}>
                  {log.status === 'success' ? '成功' : '失败'}
                </Text>
              </View>
              <Text style={[styles.logMessage, { color: colors.textSecondary }]} numberOfLines={2}>{log.message}</Text>
              <Text style={[styles.logTime, { color: colors.textMuted }]}>{formatLogTime(log.createdAt)}</Text>
            </View>
          ))
        )}
      </View>
    </ScrollView>

    {/* 远程控制确认对话框 */}
    {confirmCommand && (
      <ConfirmDialog
        visible
        title="远程控制确认"
        message={`确定要${confirmCommand.label}设备「${device?.name ?? ''}」吗？`}
        confirmLabel={`确认${confirmCommand.label}`}
        cancelLabel="取消"
        loading={controlling}
        danger={confirmCommand.danger}
        onConfirm={executeControl}
        onCancel={() => {
          if (!controlling) setConfirmCommand(null);
        }}
      />
    )}
    </>
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
  infoCard: {
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
    marginBottom: 16,
  },
  infoHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  deviceIcon: {
    fontSize: 32,
    marginRight: 12,
  },
  infoHeaderContent: {
    flex: 1,
  },
  deviceName: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 2,
  },
  deviceCode: {
    fontSize: 13,
  },
  infoDivider: {
    height: 1,
    marginVertical: 12,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
  },
  infoLabel: {
    fontSize: 14,
  },
  infoValue: {
    fontSize: 14,
    fontWeight: '500',
  },
  section: {
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 10,
  },
  telemetryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  telemetryCard: {
    borderRadius: 12,
    padding: 14,
    width: '30%',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  telemetryValue: {
    fontSize: 22,
    fontWeight: '700',
  },
  telemetryUnit: {
    fontSize: 11,
    marginTop: 2,
  },
  telemetryLabel: {
    fontSize: 11,
    marginTop: 2,
  },
  telemetryTime: {
    fontSize: 12,
    textAlign: 'right',
    marginTop: 8,
  },
  controlGrid: {
    flexDirection: 'row',
    gap: 10,
  },
  controlBtn: {
    flex: 1,
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    minHeight: 60,
    justifyContent: 'center',
  },
  controlIcon: {
    fontSize: 20,
    marginBottom: 4,
  },
  controlLabel: {
    fontSize: 13,
    fontWeight: '500',
  },
  logHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  clearLogText: {
    fontSize: 13,
  },
  logEmpty: {
    fontSize: 13,
    textAlign: 'center',
    paddingVertical: 20,
    borderRadius: 8,
  },
  logItem: {
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
    borderLeftWidth: 3,
  },
  logRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  logCommand: {
    fontSize: 14,
    fontWeight: '600',
  },
  logStatus: {
    fontSize: 12,
    fontWeight: '600',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
    overflow: 'hidden',
  },
  logMessage: {
    fontSize: 12,
    lineHeight: 18,
    marginBottom: 4,
  },
  logTime: {
    fontSize: 11,
  },
});

export default DeviceDetailScreen;
