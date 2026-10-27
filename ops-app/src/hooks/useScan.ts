import { useState, useCallback, useRef } from 'react';
import { scanApi } from '../services/api';
import { ScanResult } from '../types';

/**
 * 扫码查询 hook — 封装设备/站点扫码查询 + 签到 + 报修逻辑。
 *
 * 职责：
 * - 管理输入/加载/结果/错误状态
 * - 调用 scanApi.scan 查询设备
 * - 提供 checkIn 和 reportFault 操作
 *
 * 返回纯数据 + 操作函数，UI 层负责 Alert 交互。
 */
export function useScan() {
  const [codeInput, setCodeInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [lastResult, setLastResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<import('react-native').TextInput>(null);

  const handleScan = useCallback(async () => {
    const code = codeInput.trim();
    if (!code) {
      setError('请输入设备/站点编码');
      return;
    }

    setLoading(true);
    setError(null);
    setLastResult(null);

    try {
      const response = await scanApi.scan(code);
      setLastResult(response.data);
      setCodeInput('');
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as {
          response?: { data?: { message?: string } };
        };
        setError(
          axiosErr.response?.data?.message || '未找到匹配的设备或站点',
        );
      } else {
        setError('网络错误，请检查网络连接');
      }
    } finally {
      setLoading(false);
    }
  }, [codeInput]);

  const handleQuickInput = useCallback((code: string) => {
    setCodeInput(code);
    setError(null);
  }, []);

  const performCheckIn = useCallback(async (): Promise<boolean> => {
    if (!lastResult) return false;
    setLoading(true);
    try {
      await scanApi.checkIn(lastResult.id);
      return true;
    } catch {
      return false;
    } finally {
      setLoading(false);
    }
  }, [lastResult]);

  return {
    codeInput,
    loading,
    lastResult,
    error,
    inputRef,
    setCodeInput,
    setError,
    handleScan,
    handleQuickInput,
    performCheckIn,
  };
}
