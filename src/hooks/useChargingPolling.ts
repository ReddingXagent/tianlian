import { useEffect, useRef, useCallback, useState } from 'react';
import { chargingApi } from '../services/api';
import { ChargingStatus } from '../types';

interface UseChargingPollingOptions {
  orderId: number;
  interval?: number; // ms, default 3000
  enabled?: boolean;
  onStatusChange?: (status: ChargingStatus) => void;
  onComplete?: (status: ChargingStatus) => void;
  onError?: (error: Error) => void;
}

interface UseChargingPollingReturn {
  status: ChargingStatus | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

/**
 * Hook for polling charging status in real time.
 *
 * Automatically polls the charging API every `interval` ms.
 * When charging completes (status !== 'charging'), polling stops
 * and `onComplete` is called.
 */
export function useChargingPolling({
  orderId,
  interval = 3000,
  enabled = true,
  onStatusChange,
  onComplete,
  onError,
}: UseChargingPollingOptions): UseChargingPollingReturn {
  const [status, setStatus] = useState<ChargingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onCompleteRef = useRef(onComplete);
  const onStatusChangeRef = useRef(onStatusChange);
  const onErrorRef = useRef(onError);

  // Keep callback refs current
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);
  useEffect(() => {
    onStatusChangeRef.current = onStatusChange;
  }, [onStatusChange]);
  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  const fetchStatus = useCallback(async () => {
    try {
      const response = await chargingApi.getStatus(orderId);
      const data = response.data;
      setStatus(data);
      setLoading(false);
      setError(null);

      onStatusChangeRef.current?.(data);

      if (data.status !== 'charging') {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        onCompleteRef.current?.(data);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取充电状态失败';
      setError(message);
      setLoading(false);
      if (err instanceof Error) {
        onErrorRef.current?.(err);
      }
    }
  }, [orderId]);

  const refresh = useCallback(async () => {
    setLoading(true);
    await fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    if (!enabled) return;

    fetchStatus();

    intervalRef.current = setInterval(fetchStatus, interval);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [orderId, interval, enabled, fetchStatus]);

  return { status, loading, error, refresh };
}

/**
 * Hook to check for an active charging session on mount.
 * Used to resume charging monitoring if app was closed during charging.
 */
export function useActiveCharging() {
  const [activeOrderId, setActiveOrderId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const checkActive = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await chargingApi.getActiveOrder();
      if (response.data) {
        setActiveOrderId(response.data.orderId);
      } else {
        setActiveOrderId(null);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '检查进行中充电失败';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkActive();
  }, [checkActive]);

  return { activeOrderId, loading, error, checkActive };
}