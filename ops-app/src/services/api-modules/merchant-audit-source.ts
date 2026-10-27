/**
 * api-modules/merchant-audit-source.ts — 商户进件审核数据通道开关 (卡 a8ca56aa ops-app 审核侧)
 * 默认 mock (云端契约未定); 契约落地后 EXPO_PUBLIC_MERCHANT_KYC_MODE=real 切换
 * (与 station-app 提交侧共用同一环境变量开关, 云端一次落地两端一起切)
 */
import { isAxiosError } from 'axios';
import type {
  MerchantApplication,
  MerchantApplicationList,
  MerchantApplicationStatus,
} from '../../types';
import { merchantAuditMockApi } from './merchant-audit-mock';

/**
 * 契约客户端懒加载: mock 为默认通道, 顶层不 import merchant-audit.ts,
 * 避免导航测试链经 client.ts 拉入原生依赖 (expo-secure-store).
 * (jest 环境不支持动态 import, 用同步 require; Metro/RN 同样支持)
 */
function loadContractApi() {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const mod = require('./merchant-audit') as typeof import('./merchant-audit');
  return mod.merchantAuditApi;
}

export type MerchantAuditMode = 'mock' | 'real';

/**
 * 归一化客户端接口: 屏/hook 只面向领域对象, envelope 解包与 404 语义收口在适配层.
 * (env 经参数注入而非字面量读取, 与 station-app merchant-source 同型, 便于测试)
 */
export interface MerchantAuditClient {
  listApplications(status?: MerchantApplicationStatus): Promise<MerchantApplicationList>;
  getApplication(id: number): Promise<MerchantApplication | null>;
  approve(id: number): Promise<MerchantApplication>;
  reject(id: number, reason: string): Promise<MerchantApplication>;
}

export function resolveMerchantAuditMode(
  env: { EXPO_PUBLIC_MERCHANT_KYC_MODE?: string } = process.env
): MerchantAuditMode {
  return env.EXPO_PUBLIC_MERCHANT_KYC_MODE === 'real' ? 'real' : 'mock';
}

export function merchantAuditModeLabel(mode: MerchantAuditMode): string {
  return mode === 'real' ? '云端通道' : '模拟通道（契约未定）';
}

/** 真实契约适配层: envelope → 领域对象; GET 404 → null (申请不存在) */
export const realMerchantAuditAdapter: MerchantAuditClient = {
  listApplications(
    status?: MerchantApplicationStatus
  ): Promise<MerchantApplicationList> {
    const merchantAuditApi = loadContractApi();
    return merchantAuditApi
      .getList({ status })
      .then((res) => res.data);
  },
  getApplication(id: number): Promise<MerchantApplication | null> {
    const merchantAuditApi = loadContractApi();
    return merchantAuditApi.getApplication(id).then(
      (res) => res.data,
      (e: unknown) => {
        if (isAxiosError(e) && e.response?.status === 404) return null;
        throw e;
      }
    );
  },
  approve(id: number): Promise<MerchantApplication> {
    const merchantAuditApi = loadContractApi();
    return merchantAuditApi.approve(id).then((res) => res.data);
  },
  reject(id: number, reason: string): Promise<MerchantApplication> {
    const merchantAuditApi = loadContractApi();
    return merchantAuditApi.reject(id, reason).then((res) => res.data);
  },
};

export function createMerchantAuditClient(mode: MerchantAuditMode): MerchantAuditClient {
  return mode === 'real' ? realMerchantAuditAdapter : merchantAuditMockApi;
}

export const MERCHANT_AUDIT_MODE: MerchantAuditMode = resolveMerchantAuditMode();
export const merchantAudit: MerchantAuditClient = createMerchantAuditClient(MERCHANT_AUDIT_MODE);
