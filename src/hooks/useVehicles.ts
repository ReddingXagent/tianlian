import { useState, useCallback, useEffect } from 'react';
import { useIsFocused } from '@react-navigation/native';
import { vehicleApi } from '../services/api';
import { Vehicle } from '../types';

interface UseVehiclesReturn {
  vehicles: Vehicle[];
  loading: boolean;
  error: string | null;
  refreshing: boolean;
  loadVehicles: () => Promise<void>;
  handleRefresh: () => Promise<void>;
  addVehicle: (data: {
    plate: string;
    brand: string;
    model: string;
    color: string;
    vin: string;
    isDefault: boolean;
  }) => Promise<{ success: boolean; errorMessage?: string; isNetworkError?: boolean }>;
  removeVehicle: (id: number) => Promise<boolean>;
  setDefaultVehicle: (id: number) => Promise<boolean>;
}

export function useVehicles(): UseVehiclesReturn {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadVehicles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await vehicleApi.getList();
      setVehicles(response.data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取车辆列表失败';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const isFocused = useIsFocused();

  useEffect(() => {
    if (isFocused) {
      let cancelled = false;
      Promise.resolve().then(() => {
        if (!cancelled) loadVehicles();
      });
      return () => { cancelled = true; };
    }
  }, [isFocused, loadVehicles]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadVehicles();
    setRefreshing(false);
  };

  const addVehicle = async (data: {
    plate: string;
    brand: string;
    model: string;
    color: string;
    vin: string;
    isDefault: boolean;
  }): Promise<{ success: boolean; errorMessage?: string; isNetworkError?: boolean }> => {
    try {
      await vehicleApi.add(data);
      loadVehicles();
      return { success: true };
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { message?: string } } };
        return { success: false, errorMessage: axiosErr.response?.data?.message };
      }
      return { success: false, isNetworkError: true };
    }
  };

  const removeVehicle = async (id: number): Promise<boolean> => {
    try {
      await vehicleApi.remove(id);
      loadVehicles();
      return true;
    } catch {
      return false;
    }
  };

  const setDefaultVehicle = async (id: number): Promise<boolean> => {
    try {
      await vehicleApi.setDefault(id);
      loadVehicles();
      return true;
    } catch {
      return false;
    }
  };

  return {
    vehicles,
    loading,
    error,
    refreshing,
    loadVehicles,
    handleRefresh,
    addVehicle,
    removeVehicle,
    setDefaultVehicle,
  };
}
