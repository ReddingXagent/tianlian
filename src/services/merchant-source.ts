/**
 * services/merchant-source.ts — 商户进件数据通道开关 (卡 a8ca56aa)
 * 默认 mock (云端契约未定); 契约落地后 EXPO_PUBLIC_MERCHANT_KYC_MODE=real 切换
 */
import { isAxiosError } from 'axios';
import type { MerchantApplication, MerchantApplicationFormInput } from '../types';
import { merchantApi } from './merchant';
import { merchantMockApi } from './merchant-mock';

export type MerchantKycMode = 'mock' | 'real';

/** 归一化客户端接口: 屏/hook 只面向领域对象, envelope 解包与 404 语义收口在适配层 */
export interface MerchantKycClient {
  submitApplication(input: MerchantApplicationFormInput): Promise<MerchantApplication>;
  getApplication(id: number): Promise<MerchantApplication | null>;
}

export function resolveMerchantKycMode(
  env: { EXPO_PUBLIC_MERCHANT_KYC_MODE?: string } = process.env
): MerchantKycMode {
  return env.EXPO_PUBLIC_MERCHANT_KYC_MODE === 'real' ? 'real' : 'mock';
}

export function merchantKycModeLabel(mode: MerchantKycMode): string {
  return mode === 'real' ? '云端通道' : '模拟通道（契约未定）';
}

/** 真实契约适配层: envelope → 领域对象; GET 404 → null (无申请) */
export const realMerchantAdapter: MerchantKycClient = {
  async submitApplication(input: MerchantApplicationFormInput): Promise<MerchantApplication> {
    const res = await merchantApi.submitApplication(input);
    return res.data;
  },
  async getApplication(id: number): Promise<MerchantApplication | null> {
    try {
      const res = await merchantApi.getApplication(id);
      return res.data;
    } catch (e) {
      if (isAxiosError(e) && e.response?.status === 404) return null;
      throw e;
    }
  },
};

export function createMerchantKycClient(mode: MerchantKycMode): MerchantKycClient {
  return mode === 'real' ? realMerchantAdapter : merchantMockApi;
}

export const MERCHANT_KYC_MODE: MerchantKycMode = resolveMerchantKycMode();
export const merchantKyc: MerchantKycClient = createMerchantKycClient(MERCHANT_KYC_MODE);
