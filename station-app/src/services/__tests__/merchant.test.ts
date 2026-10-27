/**
 * services/merchant.test.ts — 云端契约客户端测试 (卡 a8ca56aa)
 * multipart 组装 + envelope 解包 + snake→camel 映射; jest FormData 为 undici 形态,
 * 文件部件断言以字段名存在性为准 (RN 原生 {uri,name,type} 序列化差异已注明)
 */
import MockAdapter from 'axios-mock-adapter';
import * as SecureStore from 'expo-secure-store';
import api from '../client';
import {
  buildMerchantFormData,
  mapMerchantApplication,
  merchantApi,
  merchantStatusLabel,
  MERCHANT_STATUS_LABEL,
  type RawMerchantApplication,
} from '../merchant';
import { EMPTY_MERCHANT_FORM } from '../../utils/merchant-kyc';
import type { MerchantApplicationFormInput } from '../../types';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);

const FORM: MerchantApplicationFormInput = {
  companyName: '测试能源有限公司',
  uscc: '91440300MA5ABC1234',
  contactName: '张三',
  contactPhone: '13800138000',
  bankName: '工商银行深圳分行',
  bankAccount: '1234567890',
  photos: {
    license: 'file://license.jpg',
    idCardFront: 'file://id-front.jpg',
    idCardBack: 'file://id-back.jpg',
    bankCard: 'file://bank.jpg',
  },
};

const RAW: RawMerchantApplication = {
  id: 88,
  status: 'audit',
  submitted_at: '2026-10-23T10:00:00Z',
  updated_at: '2026-10-23T11:00:00Z',
  reject_reason: null,
  company_name: '测试能源有限公司',
  uscc: '91440300MA5ABC1234',
  contact_name: '张三',
  contact_phone: '13800138000',
  bank_name: '工商银行深圳分行',
  bank_account: '1234567890',
  license_photo: 'file://license.jpg',
  id_card_front_photo: 'file://id-front.jpg',
  id_card_back_photo: null,
  bank_card_photo: 'file://bank.jpg',
};

beforeEach(() => {
  jest.clearAllMocks();
  mockAxios.reset();
});

describe('mapMerchantApplication', () => {
  it('全字段 snake→camel 映射, null 证照保留', () => {
    const app = mapMerchantApplication(RAW);
    expect(app.id).toBe(88);
    expect(app.status).toBe('audit');
    expect(app.submittedAt).toBe('2026-10-23T10:00:00Z');
    expect(app.form.companyName).toBe('测试能源有限公司');
    expect(app.form.photos.license).toBe('file://license.jpg');
    expect(app.form.photos.idCardBack).toBeNull();
    expect(app.rejectReason).toBeNull();
  });

  it('空对象兜底: id=0 / status=pending / 证照全 null', () => {
    const app = mapMerchantApplication({});
    expect(app.id).toBe(0);
    expect(app.status).toBe('pending');
    expect(app.submittedAt).toBe('');
    expect(app.form.companyName).toBe('');
    expect(Object.values(app.form.photos).every((v) => v === null)).toBe(true);
  });

  it('状态别名归一: auditing/reviewing → audit, 未知 → pending', () => {
    expect(mapMerchantApplication({ status: 'auditing' }).status).toBe('audit');
    expect(mapMerchantApplication({ status: 'reviewing' }).status).toBe('audit');
    expect(mapMerchantApplication({ status: 'weird_state' }).status).toBe('pending');
  });
});

describe('MERCHANT_STATUS_LABEL / merchantStatusLabel', () => {
  it('四态中文标签齐全', () => {
    expect(merchantStatusLabel('pending')).toBe('待审核');
    expect(merchantStatusLabel('audit')).toBe('审核中');
    expect(merchantStatusLabel('rejected')).toBe('已驳回');
    expect(merchantStatusLabel('approved')).toBe('已通过');
    expect(Object.keys(MERCHANT_STATUS_LABEL)).toHaveLength(4);
  });
});

describe('buildMerchantFormData', () => {
  it('表单字段以 snake_case 全量入 multipart', () => {
    const fd = buildMerchantFormData(FORM);
    expect(fd.get('company_name')).toBe('测试能源有限公司');
    expect(fd.get('uscc')).toBe('91440300MA5ABC1234');
    expect(fd.get('contact_name')).toBe('张三');
    expect(fd.get('contact_phone')).toBe('13800138000');
    expect(fd.get('bank_name')).toBe('工商银行深圳分行');
    expect(fd.get('bank_account')).toBe('1234567890');
  });

  it('四证照 part 存在 (RN {uri,name,type} 文件部件)', () => {
    const fd = buildMerchantFormData(FORM);
    expect(fd.has('license_photo')).toBe(true);
    expect(fd.has('id_card_front_photo')).toBe(true);
    expect(fd.has('id_card_back_photo')).toBe(true);
    expect(fd.has('bank_card_photo')).toBe(true);
  });

  it('证照缺失时不追加空部件', () => {
    const fd = buildMerchantFormData({ ...FORM, photos: EMPTY_MERCHANT_FORM.photos });
    expect(fd.has('license_photo')).toBe(false);
    expect(fd.has('id_card_front_photo')).toBe(false);
    expect(fd.has('id_card_back_photo')).toBe(false);
    expect(fd.has('bank_card_photo')).toBe(false);
  });

  it('字段值提交前 trim', () => {
    const fd = buildMerchantFormData({ ...FORM, companyName: '  测试能源有限公司  ' });
    expect(fd.get('company_name')).toBe('测试能源有限公司');
  });
});

describe('merchantApi', () => {
  it('submitApplication: POST multipart 契约路径 + envelope 解包映射', async () => {
    let captured: { url?: string; method?: string; headers?: unknown } = {};
    mockAxios.onPost('/business/merchant-applications').reply((config) => {
      captured = { url: config.url, method: config.method, headers: config.headers };
      return [200, { code: 200, message: 'success', data: RAW }];
    });
    const res = await merchantApi.submitApplication(FORM);
    expect(captured.url).toBe('/business/merchant-applications');
    expect(captured.method).toBe('post');
    const headers = captured.headers as { get?: (k: string) => string } | undefined;
    const ct = headers?.get?.('Content-Type') ?? '';
    expect(String(ct)).toContain('multipart/form-data');
    expect(res.code).toBe(200);
    expect(res.data.status).toBe('audit');
    expect(res.data.form.uscc).toBe('91440300MA5ABC1234');
  });

  it('submitApplication: envelope 无 data → 兜底映射 (status=pending)', async () => {
    mockAxios.onPost('/business/merchant-applications').reply(200, { code: 200, message: 'success' });
    const res = await merchantApi.submitApplication(FORM);
    expect(res.data.status).toBe('pending');
    expect(res.data.id).toBe(0);
  });

  it('getApplication: GET /:id + 映射', async () => {
    mockAxios.onGet('/business/merchant-applications/88').reply(200, {
      code: 200,
      message: 'success',
      data: { ...RAW, status: 'rejected', reject_reason: '执照模糊' },
    });
    const res = await merchantApi.getApplication(88);
    expect(res.data.status).toBe('rejected');
    expect(res.data.rejectReason).toBe('执照模糊');
  });

  it('getApplication: envelope 无 data → 兜底映射', async () => {
    mockAxios.onGet('/business/merchant-applications/88').reply(200, { code: 200, message: 'success' });
    const res = await merchantApi.getApplication(88);
    expect(res.data.status).toBe('pending');
    expect(res.data.id).toBe(0);
  });

  it('getApplication: 404 按契约抛出 (null 语义由 source 适配层收口)', async () => {
    mockAxios.onGet('/business/merchant-applications/999').reply(404, { code: 404, message: 'not found' });
    await expect(merchantApi.getApplication(999)).rejects.toBeDefined();
  });
});
