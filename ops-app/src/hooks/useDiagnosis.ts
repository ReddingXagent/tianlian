import { useState, useCallback } from 'react';
import { diagnosisApi } from '../services/api';
import { DiagnosisResult } from '../types';

/**
 * 故障码诊断 hook — 封装故障码查询逻辑。
 *
 * 职责：
 * - 管理输入/加载/结果/错误状态
 * - 调用 diagnosisApi.getDiagnosis
 * - 提供快速输入辅助函数
 */
export function useDiagnosis() {
  const [codeInput, setCodeInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DiagnosisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = useCallback(async () => {
    const code = codeInput.trim();
    if (!code) {
      setError('请输入故障码');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await diagnosisApi.getDiagnosis(code);
      setResult(response.data);
      setCodeInput('');
    } catch {
      setError('未找到该故障码，请确认故障码是否正确');
    } finally {
      setLoading(false);
    }
  }, [codeInput]);

  const handleQuickInput = useCallback((code: string) => {
    setCodeInput(code);
    setError(null);
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return {
    codeInput,
    loading,
    result,
    error,
    setCodeInput,
    clearError,
    handleSearch,
    handleQuickInput,
  };
}
