/**
 * merchant-audit-mock.test.ts — 商户进件审核 mock 通道状态机测试 (卡 a8ca56aa)
 * 覆盖: 种子列表/状态过滤、详情命中/未命中、approve/reject 状态推进、
 *       终态不可再审、reset 恢复、seed 注入
 */
import {
  merchantAuditMockApi,
  __mockStore as merchantAuditMockStore,
  MerchantAuditInvalidTransitionError,
  MerchantAuditNotFoundError,
} from '../api-modules/merchant-audit-mock';

const findApp = (id: number) =>
  merchantAuditMockStore.current.find((a) => a.id === id)!;

beforeEach(() => {
  merchantAuditMockStore.reset();
});

describe('merchant-audit-mock — listApplications', () => {
  it('seeds four applications covering all statuses', async () => {
    const list = await merchantAuditMockApi.listApplications();
    expect(list.items).toHaveLength(4);
    expect(list.total).toBe(4);
    const statuses = list.items.map((a) => a.status).sort();
    expect(statuses).toEqual(['approved', 'audit', 'pending', 'rejected']);
  });

  it('filters by status', async () => {
    const list = await merchantAuditMockApi.listApplications('pending');
    expect(list.items).toHaveLength(1);
    expect(list.items[0].status).toBe('pending');
  });
});

describe('merchant-audit-mock — getApplication', () => {
  it('returns clone of existing application', async () => {
    const app = await merchantAuditMockApi.getApplication(1001);
    expect(app.id).toBe(1001);
    expect(app.status).toBe('pending');
    // clone: 修改返回值不影响内部 store
    app.form.companyName = '篡改';
    expect(findApp(1001).form.companyName).not.toBe('篡改');
  });

  it('throws NotFoundError for missing id', async () => {
    await expect(merchantAuditMockApi.getApplication(9999)).rejects.toBeInstanceOf(
      MerchantAuditNotFoundError
    );
  });
});

describe('merchant-audit-mock — approve/reject transitions', () => {
  it('approves pending application', async () => {
    const app = await merchantAuditMockApi.approve(1001);
    expect(app.status).toBe('approved');
    expect(findApp(1001).status).toBe('approved');
  });

  it('approves audit application', async () => {
    const app = await merchantAuditMockApi.approve(1002);
    expect(app.status).toBe('approved');
  });

  it('rejects audit application with reason', async () => {
    const app = await merchantAuditMockApi.reject(1002, '证件过期');
    expect(app.status).toBe('rejected');
    expect(app.rejectReason).toBe('证件过期');
    expect(findApp(1002).rejectReason).toBe('证件过期');
  });

  it('refuses to approve terminal approved application', async () => {
    await expect(merchantAuditMockApi.approve(1004)).rejects.toBeInstanceOf(
      MerchantAuditInvalidTransitionError
    );
  });

  it('refuses to reject terminal rejected application', async () => {
    await expect(merchantAuditMockApi.reject(1003, '再驳一次')).rejects.toBeInstanceOf(
      MerchantAuditInvalidTransitionError
    );
  });

  it('throws NotFoundError when approving missing id', async () => {
    await expect(merchantAuditMockApi.approve(4242)).rejects.toBeInstanceOf(
      MerchantAuditNotFoundError
    );
  });

  it('throws NotFoundError when rejecting missing id', async () => {
    await expect(merchantAuditMockApi.reject(4242, 'x')).rejects.toBeInstanceOf(
      MerchantAuditNotFoundError
    );
  });
});

describe('merchant-audit-mock — store injection', () => {
  it('reset restores seed state after mutations', async () => {
    await merchantAuditMockApi.approve(1001);
    expect(findApp(1001).status).toBe('approved');
    merchantAuditMockStore.reset();
    expect(findApp(1001).status).toBe('pending');
    expect(merchantAuditMockStore.current).toHaveLength(4);
  });

  it('seed replaces store contents', async () => {
    const custom = {
      id: 2001,
      status: 'audit' as const,
      submittedAt: '2026-10-24T00:00:00Z',
      updatedAt: '2026-10-24T00:00:00Z',
      rejectReason: null,
      form: {
        companyName: '注入公司',
        uscc: '91330100MA2H9B5B9Z',
        contactName: '李四',
        contactPhone: '13900000000',
        bankName: '建设银行',
        bankAccount: '6217001234567890',
        photos: { license: null, idCardFront: null, idCardBack: null, bankCard: null },
      },
    };
    merchantAuditMockStore.seed([custom]);
    const list = await merchantAuditMockApi.listApplications();
    expect(list.items).toHaveLength(1);
    expect(list.items[0].form.companyName).toBe('注入公司');
    merchantAuditMockStore.reset();
    expect(merchantAuditMockStore.current).toHaveLength(4);
  });
});
