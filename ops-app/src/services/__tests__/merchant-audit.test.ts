/**
 * merchant-audit.test.ts — 商户进件审核契约客户端测试 (卡 a8ca56aa ops-app 审核侧)
 * 覆盖: 字段映射全量/缺省、状态别名归一、未识别回落、列表双形态解包、
 *       四个端点 URL/参数/payload/envelope 解包
 */
import MockAdapter from 'axios-mock-adapter';
import api, {
  merchantAuditApi,
  mapMerchantApplication,
  mapMerchantApplicationList,
  merchantStatusLabel,
} from '../api';
import type { RawMerchantApplication } from '../api';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);

const RAW_FULL: RawMerchantApplication = {
  id: 1001,
  status: 'pending',
  submitted_at: '2026-10-24T01:00:00Z',
  updated_at: '2026-10-24T01:00:00Z',
  reject_reason: null,
  company_name: '杭州星星充电服务有限公司',
  uscc: '91330106MA2H0X9X1A',
  contact_name: '王运营',
  contact_phone: '13800000000',
  bank_name: '工商银行',
  bank_account: '1202020209876543210',
  license_photo: 'file://mock-kyc/license.jpg',
  id_card_front_photo: 'file://mock-kyc/id-card-front.jpg',
  id_card_back_photo: null,
  bank_card_photo: 'file://mock-kyc/bank-card.jpg',
};

describe('merchant-audit — mapMerchantApplication', () => {
  it('maps full raw application', () => {
    const app = mapMerchantApplication(RAW_FULL);
    expect(app.id).toBe(1001);
    expect(app.status).toBe('pending');
    expect(app.form.companyName).toBe('杭州星星充电服务有限公司');
    expect(app.form.uscc).toBe('91330106MA2H0X9X1A');
    expect(app.form.photos.license).toBe('file://mock-kyc/license.jpg');
    expect(app.form.photos.idCardBack).toBeNull();
    expect(app.form.photos.bankCard).toBe('file://mock-kyc/bank-card.jpg');
  });

  it('tolerates missing fields with defaults', () => {
    const app = mapMerchantApplication({});
    expect(app.id).toBe(0);
    expect(app.status).toBe('pending');
    expect(app.submittedAt).toBe('');
    expect(app.rejectReason).toBeNull();
    expect(app.form.companyName).toBe('');
    expect(app.form.photos.license).toBeNull();
  });

  it.each([
    ['audit', 'audit'],
    ['auditing', 'audit'],
    ['reviewing', 'audit'],
    ['rejected', 'rejected'],
    ['approved', 'approved'],
    ['pending', 'pending'],
  ] as const)('normalizes status %s -> %s', (raw, expected) => {
    expect(mapMerchantApplication({ status: raw }).status).toBe(expected);
  });

  it('falls back to pending for unknown status', () => {
    expect(mapMerchantApplication({ status: 'weird' }).status).toBe('pending');
    expect(mapMerchantApplication({ status: undefined }).status).toBe('pending');
  });

  it('exposes status labels', () => {
    expect(merchantStatusLabel('pending')).toBe('待审核');
    expect(merchantStatusLabel('audit')).toBe('审核中');
    expect(merchantStatusLabel('rejected')).toBe('已驳回');
    expect(merchantStatusLabel('approved')).toBe('已通过');
  });
});

describe('merchant-audit — mapMerchantApplicationList', () => {
  it('unwraps envelope { data: { items, total } }', () => {
    const list = mapMerchantApplicationList({
      code: 0,
      data: { items: [RAW_FULL], total: 7 },
    });
    expect(list.items).toHaveLength(1);
    expect(list.items[0].form.companyName).toBe('杭州星星充电服务有限公司');
    expect(list.total).toBe(7);
  });

  it('falls back to bare payload and items-length total', () => {
    const list = mapMerchantApplicationList({ items: [RAW_FULL, RAW_FULL] });
    expect(list.items).toHaveLength(2);
    expect(list.total).toBe(2);
  });

  it('returns empty list for null-ish payload', () => {
    const list = mapMerchantApplicationList(null);
    expect(list.items).toEqual([]);
    expect(list.total).toBe(0);
  });
});

describe('merchant-audit — merchantAuditApi endpoints', () => {
  beforeEach(() => {
    mockAxios.reset();
    jest.clearAllMocks();
  });

  it('getList hits list endpoint with status filter and unwraps envelope', async () => {
    mockAxios
      .onGet('/business/merchant-applications', { params: { status: 'pending' } })
      .reply(200, { code: 0, message: 'ok', data: { items: [RAW_FULL], total: 1 } });
    const res = await merchantAuditApi.getList({ status: 'pending' });
    expect(res.data.items).toHaveLength(1);
    expect(res.data.total).toBe(1);
    expect(res.data.items[0].status).toBe('pending');
  });

  it('getList without filters sends no status param', async () => {
    mockAxios
      .onGet('/business/merchant-applications', { params: {} })
      .reply(200, { code: 0, data: { items: [], total: 0 } });
    const res = await merchantAuditApi.getList();
    expect(res.data.items).toEqual([]);
  });

  it('getApplication fetches by id and maps fields', async () => {
    mockAxios
      .onGet('/business/merchant-applications/1001')
      .reply(200, { code: 0, data: RAW_FULL });
    const res = await merchantAuditApi.getApplication(1001);
    expect(res.data.id).toBe(1001);
    expect(res.data.form.contactName).toBe('王运营');
  });

  it('approve posts to approve endpoint', async () => {
    mockAxios
      .onPost('/business/merchant-applications/1001/approve')
      .reply(200, { code: 0, data: { ...RAW_FULL, status: 'approved' } });
    const res = await merchantAuditApi.approve(1001);
    expect(res.data.status).toBe('approved');
  });

  it('reject posts reject_reason payload', async () => {
    mockAxios
      .onPost('/business/merchant-applications/1001/reject', { reject_reason: '照片模糊' })
      .reply(200, {
        code: 0,
        data: { ...RAW_FULL, status: 'rejected', reject_reason: '照片模糊' },
      });
    const res = await merchantAuditApi.reject(1001, '照片模糊');
    expect(res.data.status).toBe('rejected');
    expect(res.data.rejectReason).toBe('照片模糊');
  });
});
