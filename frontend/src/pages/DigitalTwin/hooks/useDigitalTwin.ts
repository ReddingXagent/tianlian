import { useState, useEffect, useCallback } from 'react';
import { digitalTwinAPI, telemetryAPI } from '../../../api/index';
import { message } from 'antd';

interface DeviceData {
  device: {
    id: number;
    name: string;
    type: string;
    status: string;
    health_score: number;
    model?: string;
    location?: string;
    last_heartbeat?: string;
    total_run_hours?: number;
    total_generation_kwh?: number;
    total_charge_kwh?: number;
  };
  digital_twin_config: {
    id: number;
    model_type: string;
    scale_x: number;
    scale_y: number;
    scale_z: number;
    position_x: number;
    position_y: number;
    position_z: number;
    rotation_x: number;
    rotation_y: number;
    rotation_z: number;
    color_primary: string;
    color_secondary: string;
    color_accent: string;
    animations: Record<string, any>;
    status_mapping: Record<string, any>;
    created_at: string;
    updated_at: string;
  };
}

interface SceneData {
  id: number;
  station_id: number;
  name: string;
  scene_config: any;
  created_at: string;
  updated_at: string;
}

interface StationData {
  id: number;
  name: string;
  address: string;
}

interface RealtimeData {
  station_id: number;
  timestamp: string;
  devices: Record<number, {
    status: string;
    health_score: number;
    power_kw?: number;
    voltage_v?: number;
    current_a?: number;
    temperature_c?: number;
    frequency_hz?: number;
    metrics?: Record<string, number>;
  }>;
}

export interface DigitalTwinState {
  station: StationData | null;
  scene: SceneData | null;
  devices: DeviceData[];
  isLoading: boolean;
  error: Error | null;
  realtimeData: RealtimeData | null;
}

export const useDigitalTwin = (stationId: number) => {
  const [state, setState] = useState<DigitalTwinState>({
    station: null,
    scene: null,
    devices: [],
    isLoading: true,
    error: null,
    realtimeData: null,
  });

  const loadStaticData = useCallback(async () => {
    if (!stationId) {
      setState(prev => ({ ...prev, isLoading: false }));
      return;
    }

    try {
      setState(prev => ({ ...prev, isLoading: true, error: null }));

      const twinResponse = await digitalTwinAPI.getRealtime(stationId);

      const station = twinResponse.station || { id: stationId, name: '未知站点', address: '' };
      const scene = twinResponse.scene || null;
      const deviceConfigs = twinResponse.devices || [];

      const devices = deviceConfigs.map((config: any) => ({
        device: config.device,
        digital_twin_config: config.digital_twin_config,
      }));

      setState(prev => ({
        ...prev,
        station,
        scene,
        devices,
        isLoading: false,
      }));
    } catch (err: any) {
      // 静默处理：数字孪生数据加载失败写入 error state 供 UI 展示
      setState(prev => ({
        ...prev,
        error: err,
        isLoading: false,
      }));
    }
  }, [stationId]);

  const loadRealtimeData = useCallback(async () => {
    if (!stationId || !state.devices.length) return;

    try {
      const realtimeData: RealtimeData = {
        station_id: stationId,
        timestamp: new Date().toISOString(),
        devices: {},
      };

      // 批量获取设备实时数据
      const promises = state.devices.map(async (device) => {
        const deviceId = device.device.id;
        try {
          const res = await telemetryAPI.latest(deviceId);
          const latestData = res.data?.data || res.data;
          if (latestData) {
            realtimeData.devices[deviceId] = {
              status: device.device.status,
              health_score: device.device.health_score,
              power_kw: latestData.power_kw ?? 0,
              voltage_v: latestData.voltage_v ?? 0,
              current_a: latestData.current_a ?? 0,
              temperature_c: latestData.temperature_c ?? 25,
              frequency_hz: latestData.frequency_hz ?? 50,
              metrics: {
                efficiency: latestData.efficiency ?? 0,
                frequency: latestData.frequency ?? 50,
                power_factor: latestData.power_factor ?? 1,
              },
            };
          }
        } catch {
          realtimeData.devices[deviceId] = {
            status: device.device.status,
            health_score: device.device.health_score,
            power_kw: 0,
            voltage_v: 0,
            current_a: 0,
            temperature_c: 25,
            frequency_hz: 50,
            metrics: {},
          };
        }
      });

      await Promise.all(promises);
      setState(prev => ({ ...prev, realtimeData }));
    } catch {
      // 静默处理：实时数据加载失败保留上次数据
    }
  }, [stationId, state.devices]);

  useEffect(() => {
    if (stationId) {
      loadStaticData();
    }
  }, [stationId, loadStaticData]);

  // 设备列表加载完成后加载实时数据
  useEffect(() => {
    if (state.devices.length > 0 && !state.realtimeData) {
      loadRealtimeData();
    }
  }, [state.devices, loadRealtimeData]);

  const refreshData = useCallback(async () => {
    await loadStaticData();
    await loadRealtimeData();
  }, [loadStaticData, loadRealtimeData]);

  const updateDeviceConfig = useCallback(async (deviceId: number, config: any) => {
    try {
      setState(prev => {
        const updatedDevices = prev.devices.map(device => {
          if (device.device.id === deviceId) {
            return {
              ...device,
              digital_twin_config: {
                ...device.digital_twin_config,
                ...config,
              },
            };
          }
          return device;
        });
        return { ...prev, devices: updatedDevices };
      });
      message.success('设备配置已更新');
    } catch (err: any) {
      message.error(`更新失败: ${err.message}`);
      throw err;
    }
  }, []);

  const updateSceneConfig = useCallback(async (config: any) => {
    try {
      setState(prev => {
        if (prev.scene) {
          return {
            ...prev,
            scene: {
              ...prev.scene,
              scene_config: {
                ...prev.scene.scene_config,
                ...config,
              },
            },
          };
        }
        return prev;
      });
      message.success('场景配置已更新');
    } catch (err: any) {
      message.error(`更新失败: ${err.message}`);
      throw err;
    }
  }, []);

  return {
    station: state.station,
    scene: state.scene,
    devices: state.devices,
    isLoading: state.isLoading,
    error: state.error,
    realtimeData: state.realtimeData,
    refreshData,
    updateDeviceConfig,
    updateSceneConfig,
  };
};
