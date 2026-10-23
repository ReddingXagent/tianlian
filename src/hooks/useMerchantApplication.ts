/**
 * hooks/useMerchantApplication.ts — 商户进件状态机 (卡 a8ca56aa)
 * 表单态(null application) ↔ 状态态; 驳回后由屏幕预填表单重提
 */
import { useCallback, useState } from 'react';
import type { MerchantApplication, MerchantApplicationFormInput } from '../types';
import { merchantKyc } from '../services/merchant-source';

export function useMerchantApplication() {
  const [application, setApplication] = useState<MerchantApplication | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(async (input: MerchantApplicationFormInput): Promise<boolean> => {
    setSubmitting(true);
    setError(null);
    try {
      const app = await merchantKyc.submitApplication(input);
      setApplication(app);
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : '提交失败，请稍后重试');
      return false;
    } finally {
      setSubmitting(false);
    }
  }, []);

  const refresh = useCallback(async (id: number): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const latest = await merchantKyc.getApplication(id);
      if (latest) setApplication(latest);
    } catch (e) {
      setError(e instanceof Error ? e.message : '刷新失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  }, []);

  /** 驳回后回表单 (屏幕负责 setForm 预填) */
  const backToForm = useCallback(() => setApplication(null), []);

  return { application, loading, submitting, error, submit, refresh, backToForm };
}
