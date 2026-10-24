/**
 * 遥测页面数据 Hook
 *
 * 封装设备选择、最新遥测拉取、历史时序拉取与自动刷新。
 * - latest：真实值 + stats 基线 + 确定性兜底
 * - history：真实数据点优先，否则确定性兜底时序
 */
import { useState, useEffect, useCallback } from 'react';
import { message } from 'antd';
import api, { telemetryAPI } from '../../../api';
import type { TelemetryData } from '../types';
import {
  fetchBaselines,
  composeLatestTelemetry,
  isRealPoints,
  buildDeterministicHistory,
} from '../utils';

export interface TelemetryDevice {
  id: number;
  name: string;
  type?: string;
}

export function useTelemetryData() {
  const [devices, setDevices] = useState<TelemetryDevice[]>([]);
  const [deviceError, setDeviceError] = useState<string | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<number | null>(null);
  const [telemetry, setTelemetry] = useState<TelemetryData | null>(null);
  const [historyData, setHistoryData] = useState<TelemetryData[]>([]);
  const [loading, setLoading] = useState(false);
  const [detailVisible, setDetailVisible] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);

  // 拉取真实设备列表（/devices），失败走错误态，不回退假设备
  const fetchDevices = useCallback(async () => {
    try {
      setDeviceError(null);
      const res: any = await api.get('/devices');
      const items = res.data?.data?.items ?? res.data?.items ?? (Array.isArray(res.data) ? res.data : []);
      setDevices(items);
      setSelectedDevice(prev => (prev != null && items.some((d: TelemetryDevice) => d.id === prev) ? prev : items[0]?.id ?? null));
    } catch (e: any) {
      setDevices([]);
      setSelectedDevice(null);
      const text = e?.response?.data?.message || e?.response?.data?.detail || e?.message || '加载失败';
      setDeviceError(text);
      message.error('设备列表加载失败：' + text);
    }
  }, []);

  useEffect(() => { fetchDevices(); }, [fetchDevices]);

  // 获取当前遥测数据：latest 真实值 + stats 基线 + 确定性兜底（无 Math.random）
  const fetchLatestTelemetry = async () => {
    if (selectedDevice == null) return;
    setLoading(true);
    try {
      const device = devices.find(d => d.id === selectedDevice);
      if (!device) return;
      const baselines = await fetchBaselines(selectedDevice);
      let latest: any = null;
      try {
        const res: any = await telemetryAPI.latest(selectedDevice);
        latest = res.data?.data || res.data || res;
      } catch { latest = null; /* 全走兜底 */ }
      setTelemetry(composeLatestTelemetry(latest, baselines, device));
    } catch (error) {
      message.error('获取遥测数据失败');
    } finally {
      setLoading(false);
    }
  };

  // 获取历史数据：history 返回真实数据点直接用；否则 stats 基线 + 确定性兜底（无 Math.random）
  const fetchHistoryData = async () => {
    if (selectedDevice == null) return;
    try {
      let items: any[] | null = null;
      try {
        const res: any = await telemetryAPI.history(selectedDevice, { hours: 24 });
        const data = res.data?.data || res.data || res;
        const candidate = (data as any)?.items || (Array.isArray(data) ? data : null);
        if (isRealPoints(candidate)) items = candidate as any[];
      } catch { items = null; }
      if (items && items.length > 0) {
        setHistoryData(items as TelemetryData[]);
        return;
      }
      const baselines = await fetchBaselines(selectedDevice);
      setHistoryData(buildDeterministicHistory(baselines));
    } catch (error) {
      message.error('获取历史数据失败');
    }
  };

  useEffect(() => {
    fetchLatestTelemetry();
    fetchHistoryData();
  }, [selectedDevice]);

  // 自动刷新
  useEffect(() => {
    if (!autoRefresh) return;

    const timer = setInterval(fetchLatestTelemetry, 5000);
    return () => clearInterval(timer);
  }, [autoRefresh, selectedDevice]);

  return {
    devices,
    deviceError,
    fetchDevices,
    selectedDevice,
    setSelectedDevice,
    telemetry,
    historyData,
    loading,
    detailVisible,
    setDetailVisible,
    autoRefresh,
    setAutoRefresh,
    fetchLatestTelemetry,
  };
}
