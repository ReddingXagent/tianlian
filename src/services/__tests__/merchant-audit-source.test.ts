/**
 * merchant-audit-source.test.ts — 审核通道开关与 real 适配层测试 (卡 a8ca56aa)
 * 覆盖: mode 解析(参数注入 env)、mode 标签、client 工厂分发、
 *       real 适配层 envelope 解包、GET 404→null、非 404 透传、approve/reject 映射
 */
import MockAdapter from 'axios-mock-adapter';
import api, {
  merchantAuditMockApi,
  resolveMerchantAuditMode,
  merchantAuditModeLabel,
  createMerchantAuditClient,
  realMerchantAuditAdapter,
  MERCHANT_AUDIT_MODE,
  merchantAudit,
} from '../api';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);

const RAW = {
  id: 1001,
  status: 'audit',
  submitted_at: '2026-10-24T01:00:00Z',
  updated_at: '2026-10-24T01:00:00Z',
  reject_reason: null,
  company_name: '杭州星星充电服务有限公司',
  uscc: '91330106MA2H0X9X1A',
  contact_name: '王运营',
  contact_phone: '13800000000',
  bank_name: '工商银行',
  bank_account: '1202020209876543210',
};

describe('merchant-audit-source — mode resolution', () => {
  it('resolves real only for explicit real value', () => {
    expect(resolveMerchantAuditMode({ EXPO_PUBLIC_MERCHANT_KYC_MODE: 'real' })).toBe('real');
    expect(resolveMerchantAuditMode({ EXPO_PUBLIC_MERCHANT_KYC_MODE: 'mock' })).toBe('mock');
    expect(resolveMerchantAuditMode({ EXPO_PUBLIC_MERCHANT_KYC_MODE: undefined })).toBe('mock');
    expect(resolveMerchantAuditMode({})).toBe('mock');
  });

  it('labels modes for UI', () => {
    expect(merchantAuditModeLabel('real')).toBe('云端通道');
    expect(merchantAuditModeLabel('mock')).toBe('模拟通道（契约未定）');
  });

  it('factory dispatches to mock or real client', () => {
    expect(createMerchantAuditClient('mock')).toBe(merchantAuditMockApi);
    expect(createMerchantAuditClient('real')).toBe(realMerchantAuditAdapter);
  });

  it('default exports resolve to mock channel in test env', () => {
    expect(MERCHANT_AUDIT_MODE).toBe('mock');
    expect(merchantAudit).toBe(merchantAuditMockApi);
  });
});

describe('merchant-audit-source — real adapter', () => {
  beforeEach(() => {
    mockAxios.reset();
    jest.clearAllMocks();
  });

  it('listApplications unwraps envelope', async () => {
    mockAxios
      .onGet('/business/merchant-applications')
      .reply(200, { code: 0, data: { items: [RAW], total: 1 } });
    const list = await realMerchantAuditAdapter.listApplications();
    expect(list.total).toBe(1);
    expect(list.items[0].form.companyName).toBe('杭州星星充电服务有限公司');
  });

  it('getApplication maps detail envelope', async () => {
    mockAxios
      .onGet('/business/merchant-applications/1001')
      .reply(200, { code: 0, data: RAW });
    const app = await realMerchantAuditAdapter.getApplication(1001);
    expect(app?.id).toBe(1001);
    expect(app?.status).toBe('audit');
  });

  it('getApplication returns null on 404', async () => {
    mockAxios.onGet('/business/merchant-applications/4040').reply(404, { code: 404 });
    await expect(realMerchantAuditAdapter.getApplication(4040)).resolves.toBeNull();
  });

  it('getApplication rethrows non-404 errors', async () => {
    mockAxios.onGet('/business/merchant-applications/5000').reply(500, { code: 500 });
    await expect(realMerchantAuditAdapter.getApplication(5000)).rejects.toThrow();
  });

  it('approve maps approved response', async () => {
    mockAxios
      .onPost('/business/merchant-applications/1001/approve')
      .reply(200, { code: 0, data: { ...RAW, status: 'approved' } });
    const app = await realMerchantAuditAdapter.approve(1001);
    expect(app.status).toBe('approved');
  });

  it('reject maps rejected response with reason', async () => {
    mockAxios
      .onPost('/business/merchant-applications/1001/reject')
      .reply(200, {
        code: 0,
        data: { ...RAW, status: 'rejected', reject_reason: '材料不全' },
      });
    const app = await realMerchantAuditAdapter.reject(1001, '材料不全');
    expect(app.status).toBe('rejected');
    expect(app.rejectReason).toBe('材料不全');
  });
});
