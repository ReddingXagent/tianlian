/**
 * services/merchant-mock.ts — 商户进件 mock 通道 (卡 a8ca56aa)
 * 云端契约未定前的内存实现: 提交即 pending, 状态经 __mockStore 注入推进;
 * 与 MerchantKycClient 接口同构, merchant-source 按 mode 切换.
 */
import type { MerchantApplication, MerchantApplicationFormInput, MerchantApplicationStatus } from '../types';

/** 模拟网络延迟 (ms) */
const MOCK_LATENCY_MS = 120;

let nextId = 1001;
let store: MerchantApplication | null = null;

const delay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** 测试注入/重置口 (生产代码不得调用) */
export const __mockStore = {
  reset(): void {
    store = null;
    nextId = 1001;
  },
  get current(): MerchantApplication | null {
    return store;
  },
  setStatus(status: MerchantApplicationStatus, rejectReason: string | null = null): void {
    if (store) {
      store.status = status;
      store.rejectReason = rejectReason;
      store.updatedAt = new Date().toISOString();
    }
  },
};

export const merchantMockApi = {
  async submitApplication(input: MerchantApplicationFormInput): Promise<MerchantApplication> {
    await delay(MOCK_LATENCY_MS);
    const now = new Date().toISOString();
    store = {
      id: nextId,
      status: 'pending',
      submittedAt: now,
      updatedAt: now,
      rejectReason: null,
      form: { ...input, photos: { ...input.photos } },
    };
    nextId += 1;
    return { ...store, form: { ...store.form, photos: { ...store.form.photos } } };
  },
  async getApplication(_id: number): Promise<MerchantApplication | null> {
    await delay(MOCK_LATENCY_MS);
    if (!store) return null;
    return { ...store, form: { ...store.form, photos: { ...store.form.photos } } };
  },
};
