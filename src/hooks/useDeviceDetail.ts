import { useState, useCallback, useEffect } from 'react';
import { deviceApi } from '../services/api';
import { Device, DeviceTelemetry } from '../types';

interface UseDeviceDetailParams {
  deviceId: number;
}

interface UseDeviceDetailReturn {
  device: Device | null;
  telemetry: DeviceTelemetry | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  controlling: boolean;
  fetchData: (isRefresh?: boolean) => Promise<void>;
  controlDevice: (command: string) => Promise<{ success: boolean; message?: string }>;
}

export function useDeviceDetail({ deviceId }: UseDeviceDetailParams): UseDeviceDetailReturn {
  const [device, setDevice] = useState<Device | null>(null);
  const [telemetry, setTelemetry] = useState<DeviceTelemetry | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [controlling, setControlling] = useState(false);

  const fetchData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const [deviceRes, telemetryRes] = await Promise.all([
        deviceApi.getDetail(deviceId),
        deviceApi.getTelemetry(deviceId).catch(() => null),
      ]);
      setDevice(deviceRes.data);
      if (telemetryRes) {
        setTelemetry(telemetryRes.data);
      }
    } catch {
      setError('加载设备详情失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [deviceId]);

  useEffect(() => {
    Promise.resolve().then(() => fetchData());
  }, [fetchData]);

  const controlDevice = async (command: string): Promise<{ success: boolean; message?: string }> => {
    setControlling(true);
    try {
      const response = await deviceApi.controlDevice(deviceId, command);
      const message = response.data.message;
      return { success: true, message };
    } catch {
      return { success: false };
    } finally {
      setControlling(false);
    }
  };

  return {
    device,
    telemetry,
    loading,
    refreshing,
    error,
    controlling,
    fetchData,
    controlDevice,
  };
}
