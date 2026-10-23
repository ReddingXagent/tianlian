/**
 * services/merchant-mock.test.ts — mock 通道行为测试 (卡 a8ca56aa)
 */
import { __mockStore, merchantMockApi } from '../merchant-mock';
import { EMPTY_MERCHANT_FORM } from '../../utils/merchant-kyc';
import type { MerchantApplicationFormInput } from '../../types';

const FORM: MerchantApplicationFormInput = {
  ...EMPTY_MERCHANT_FORM,
  companyName: '测试能源有限公司',
  uscc: '91440300MA5ABC1234',
  contactName: '张三',
  contactPhone: '13800138000',
  bankName: '工商银行深圳分行',
  bankAccount: '1234567890',
  photos: { ...EMPTY_MERCHANT_FORM.photos, license: 'file://license.jpg' },
};

beforeEach(() => {
  __mockStore.reset();
});

describe('merchantMockApi', () => {
  it('reset 后无申请, getApplication → null', async () => {
    expect(__mockStore.current).toBeNull();
    await expect(merchantMockApi.getApplication(1)).resolves.toBeNull();
  });

  it('提交即 pending, id 从 1001 起, 表单回显', async () => {
    const app = await merchantMockApi.submitApplication(FORM);
    expect(app.id).toBe(1001);
    expect(app.status).toBe('pending');
    expect(app.rejectReason).toBeNull();
    expect(app.form.companyName).toBe('测试能源有限公司');
    expect(app.form.photos.license).toBe('file://license.jpg');
    expect(app.submittedAt).toBe(app.updatedAt);
    expect(__mockStore.current?.id).toBe(1001);
  });

  it('再次提交 id 自增', async () => {
    await merchantMockApi.submitApplication(FORM);
    const second = await merchantMockApi.submitApplication(FORM);
    expect(second.id).toBe(1002);
  });

  it('getApplication 返回快照副本, 突变返回值不污染 store', async () => {
    await merchantMockApi.submitApplication(FORM);
    const snapshot = await merchantMockApi.getApplication(1001);
    snapshot.form.companyName = '被污染';
    snapshot.status = 'approved';
    const again = await merchantMockApi.getApplication(1001);
    expect(again.form.companyName).toBe('测试能源有限公司');
    expect(again.status).toBe('pending');
  });

  it('setStatus 注入推进: rejected 带驳回原因 + updatedAt 更新', async () => {
    await merchantMockApi.submitApplication(FORM);
    __mockStore.setStatus('rejected', '执照模糊');
    const app = await merchantMockApi.getApplication(1001);
    expect(app.status).toBe('rejected');
    expect(app.rejectReason).toBe('执照模糊');
    expect(app.updatedAt >= app.submittedAt).toBe(true);
  });

  it('setStatus approved 默认无原因, 空_store 静默', async () => {
    __mockStore.setStatus('approved'); // store 为空, 不抛
    expect(__mockStore.current).toBeNull();
    await merchantMockApi.submitApplication(FORM);
    __mockStore.setStatus('approved');
    expect(__mockStore.current?.status).toBe('approved');
    expect(__mockStore.current?.rejectReason).toBeNull();
  });
});
