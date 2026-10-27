/**
 * services/merchant-source.test.ts — 通道开关与真实适配层测试 (卡 a8ca56aa)
 */
import MockAdapter from 'axios-mock-adapter';
import * as SecureStore from 'expo-secure-store';
import api from '../client';
import {
  createMerchantKycClient,
  merchantKyc,
  merchantKycModeLabel,
  MERCHANT_KYC_MODE,
  realMerchantAdapter,
  resolveMerchantKycMode,
} from '../merchant-source';
import { merchantMockApi, __mockStore } from '../merchant-mock';
import { merchantApi } from '../merchant';
import { EMPTY_MERCHANT_FORM } from '../../utils/merchant-kyc';
import type { MerchantApplicationFormInput } from '../../types';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);

const FORM: MerchantApplicationFormInput = {
  ...EMPTY_MERCHANT_FORM,
  companyName: '测试能源有限公司',
  uscc: '91440300MA5ABC1234',
  contactName: '张三',
  contactPhone: '13800138000',
  bankName: '工商银行深圳分行',
  bankAccount: '1234567890',
};

beforeEach(() => {
  jest.clearAllMocks();
  mockAxios.reset();
  __mockStore.reset();
});

describe('resolveMerchantKycMode', () => {
  it.each([
    [undefined, 'mock'],
    ['mock', 'mock'],
    ['', 'mock'],
    ['off', 'mock'],
    ['real', 'real'],
  ] as const)('env=%s → %s', (value, expected) => {
    expect(resolveMerchantKycMode({ EXPO_PUBLIC_MERCHANT_KYC_MODE: value })).toBe(expected);
  });

  it('缺省读 process.env, 非 real 一律 mock', () => {
    expect(resolveMerchantKycMode()).toBe('mock');
  });
});

describe('merchantKycModeLabel', () => {
  it('两态标签', () => {
    expect(merchantKycModeLabel('mock')).toContain('模拟');
    expect(merchantKycModeLabel('real')).toBe('云端通道');
  });
});

describe('createMerchantKycClient / 默认单例', () => {
  it('mock 模式复用 mock 实现, real 模式换真实适配层', () => {
    expect(createMerchantKycClient('mock')).toBe(merchantMockApi);
    expect(createMerchantKycClient('real')).toBe(realMerchantAdapter);
    expect(createMerchantKycClient('real')).not.toBe(merchantMockApi);
  });

  it('默认单例为 mock 通道 (契约未定)', () => {
    expect(MERCHANT_KYC_MODE).toBe('mock');
    expect(merchantKyc).toBe(merchantMockApi);
  });
});

describe('realMerchantAdapter', () => {
  it('submitApplication 解包 envelope → 领域对象', async () => {
    mockAxios.onPost('/business/merchant-applications').reply(200, {
      code: 200,
      message: 'success',
      data: { id: 7, status: 'pending', company_name: '测试能源有限公司' },
    });
    const app = await realMerchantAdapter.submitApplication(FORM);
    expect(app.id).toBe(7);
    expect(app.status).toBe('pending');
    expect(app.form.companyName).toBe('测试能源有限公司');
  });

  it('getApplication 200 → 解包领域对象', async () => {
    mockAxios.onGet('/business/merchant-applications/7').reply(200, {
      code: 200,
      message: 'success',
      data: { id: 7, status: 'approved', company_name: '测试能源有限公司' },
    });
    const app = await realMerchantAdapter.getApplication(7);
    expect(app?.id).toBe(7);
    expect(app?.status).toBe('approved');
  });

  it('getApplication 404 → null (无申请语义)', async () => {
    mockAxios.onGet('/business/merchant-applications/404').reply(404, { code: 404 });
    await expect(realMerchantAdapter.getApplication(404)).resolves.toBeNull();
  });

  it('getApplication 非 404 错误原样抛出', async () => {
    mockAxios.onGet('/business/merchant-applications/500').reply(500, { code: 500 });
    await expect(realMerchantAdapter.getApplication(500)).rejects.toBeDefined();
  });

  it('getApplication 非 axios 错误穿透', async () => {
    const spy = jest.spyOn(merchantApi, 'getApplication').mockRejectedValueOnce(new Error('boom'));
    await expect(realMerchantAdapter.getApplication(1)).rejects.toThrow('boom');
    spy.mockRestore();
  });
});
