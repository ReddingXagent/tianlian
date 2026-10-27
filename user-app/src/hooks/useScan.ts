import { useState, useCallback } from 'react';
import { chargingApi } from '../services/api';
import { useOrderStore } from '../store/orderStore';
import { ScanResult, ChargingStatus } from '../types';

interface UseScanReturn {
  codeInput: string;
  setCodeInput: (text: string) => void;
  loading: boolean;
  lastResult: ScanResult | null;
  error: string | null;
  starting: boolean;
  cameraOpen: boolean;
  setCameraOpen: (open: boolean) => void;
  lookupCode: (code: string) => Promise<void>;
  handleScan: () => Promise<void>;
  handleCameraScan: (code: string) => void;
  handleStartCharging: () => Promise<ChargingStatus | undefined>;
  resetError: () => void;
}

export function useScan(): UseScanReturn {
  const [codeInput, setCodeInputState] = useState('');
  const [loading, setLoading] = useState(false);
  const [lastResult, setLastResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);
  const startCharging = useOrderStore((s) => s.startCharging);

  const setCodeInput = useCallback((text: string) => {
    setCodeInputState(text);
    setError(null);
  }, []);

  const resetError = () => setError(null);

  const lookupCode = useCallback(async (code: string) => {
    setLoading(true);
    setError(null);
    setLastResult(null);

    try {
      const response = await chargingApi.scan(code);
      setLastResult(response.data);
      setCodeInputState('');
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { message?: string } } };
        setError(axiosErr.response?.data?.message || '未找到匹配的充电桩');
      } else {
        setError('网络错误，请检查网络连接');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const handleScan = useCallback(async () => {
    const code = codeInput.trim();
    if (!code) {
      setError('请输入充电桩编码');
      return;
    }
    await lookupCode(code);
  }, [codeInput, lookupCode]);

  const handleCameraScan = useCallback(
    (code: string) => {
      setCameraOpen(false);
      setCodeInputState(code);
      setError(null);
      void lookupCode(code);
    },
    [lookupCode]
  );

  const handleStartCharging = useCallback(async () => {
    if (!lastResult) return;

    if (lastResult.status !== 'idle') {
      setError('该充电桩当前不可用');
      return;
    }

    setStarting(true);
    try {
      const status = await startCharging(lastResult.id);
      return status;
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { message?: string } } };
        setError(axiosErr.response?.data?.message || '启动充电失败');
      } else {
        setError('网络错误，请检查网络连接');
      }
      throw err;
    } finally {
      setStarting(false);
    }
  }, [lastResult, startCharging]);

  return {
    codeInput,
    setCodeInput,
    loading,
    lastResult,
    error,
    starting,
    cameraOpen,
    setCameraOpen,
    lookupCode,
    handleScan,
    handleCameraScan,
    handleStartCharging,
    resetError,
  };
}
