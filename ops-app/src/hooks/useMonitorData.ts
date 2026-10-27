import { useState, useCallback, useEffect, useRef } from 'react';
import { monitorApi, deviceMonitorApi } from '../services/api';
import {
  MonitorSummary,
  Device,
  Alarm,
  RealtimeOverview,
} from '../types';

export type MonitorTab = 'devices' | 'faults' | 'alarms';

const POLL_INTERVAL_MS = 10_000;
const PAGE_SIZE_DEVICES = 50;
const PAGE_SIZE_FAULTS = 20;

/**
 * 监控屏数据 hook — 封装概览/设备/故障/告警/实时遥测的加载与轮询。
 *
 * 职责：
 * - 首次挂载拉取全量数据（summary + devices + faults + alarms）
 * - 下拉刷新复用同一 fetch 逻辑
 * - activeTab='devices' 时启动 10s 轮询 realtime overview
 *
 * 返回纯数据 + 操作函数，不包含任何 UI。
 */
export function useMonitorData() {
  const [summary, setSummary] = useState<MonitorSummary | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [realtimeOverview, setRealtimeOverview] =
    useState<RealtimeOverview | null>(null);
  const [faultDevices, setFaultDevices] = useState<Device[]>([]);
  const [criticalAlarms, setCriticalAlarms] = useState<Alarm[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchAll = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const [summaryRes, devicesRes, faultsRes, alarmsRes] = await Promise.all([
        monitorApi.getSummary(),
        deviceMonitorApi.getDeviceStatusList({ pageSize: PAGE_SIZE_DEVICES }),
        monitorApi.getFaultDevices({ pageSize: PAGE_SIZE_FAULTS }),
        monitorApi.getCriticalAlarms({ pageSize: PAGE_SIZE_FAULTS }),
      ]);
      setSummary(summaryRes.data);
      setDevices(devicesRes.data.items);
      setFaultDevices(faultsRes.data.items);
      setCriticalAlarms(alarmsRes.data.items);
    } catch {
      setError('加载监控数据失败，请下拉刷新重试');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const fetchRealtimeMetrics = useCallback(async () => {
    if (devices.length === 0) return;
    try {
      const res = await deviceMonitorApi.getRealtimeOverview();
      setRealtimeOverview(res.data);
    } catch {
      // 实时数据获取失败，静默处理
    }
  }, [devices]);

  // 首次挂载
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [summaryRes, devicesRes, faultsRes, alarmsRes] =
          await Promise.all([
            monitorApi.getSummary(),
            deviceMonitorApi.getDeviceStatusList({
              pageSize: PAGE_SIZE_DEVICES,
            }),
            monitorApi.getFaultDevices({ pageSize: PAGE_SIZE_FAULTS }),
            monitorApi.getCriticalAlarms({ pageSize: PAGE_SIZE_FAULTS }),
          ]);
        if (cancelled) return;
        setSummary(summaryRes.data);
        setDevices(devicesRes.data.items);
        setFaultDevices(faultsRes.data.items);
        setCriticalAlarms(alarmsRes.data.items);
      } catch {
        if (cancelled) return;
        setError('加载监控数据失败，请下拉刷新重试');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // 实时轮询（仅 devices tab 有设备时）
  const startPolling = useCallback(
    (active: boolean) => {
      if (active && devices.length > 0) {
        void fetchRealtimeMetrics();
        refreshTimer.current = setInterval(() => {
          void fetchRealtimeMetrics();
        }, POLL_INTERVAL_MS);
      }
      return () => {
        if (refreshTimer.current) {
          clearInterval(refreshTimer.current);
          refreshTimer.current = null;
        }
      };
    },
    [devices.length, fetchRealtimeMetrics],
  );

  return {
    summary,
    devices,
    faultDevices,
    criticalAlarms,
    realtimeOverview,
    loading,
    refreshing,
    error,
    fetchAll,
    startPolling,
  };
}
