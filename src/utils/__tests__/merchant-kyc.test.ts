/**
 * utils/merchant-kyc.test.ts — 表单纯函数穷举测试 (卡 a8ca56aa)
 */
import {
  EMPTY_MERCHANT_FORM,
  MERCHANT_PHOTO_SLOTS,
  MERCHANT_TEXT_FIELDS,
  pickMockPhotoUri,
  validateMerchantForm,
} from '../merchant-kyc';
import type { MerchantApplicationFormInput } from '../../types';

const VALID: MerchantApplicationFormInput = {
  companyName: '测试能源有限公司',
  uscc: '91440300MA5ABC1234',
  contactName: '张三',
  contactPhone: '13800138000',
  bankName: '工商银行深圳分行',
  bankAccount: '1234567890',
  photos: {
    license: 'file://mock-kyc/license.jpg',
    idCardFront: 'file://mock-kyc/idCardFront.jpg',
    idCardBack: 'file://mock-kyc/idCardBack.jpg',
    bankCard: 'file://mock-kyc/bankCard.jpg',
  },
};

describe('validateMerchantForm', () => {
  it('全量合法 → 零错误', () => {
    expect(Object.keys(validateMerchantForm(VALID))).toHaveLength(0);
  });

  it('空表单 → 7 项错误 (6 字段 + 证照)', () => {
    const errs = validateMerchantForm(EMPTY_MERCHANT_FORM);
    expect(Object.keys(errs).sort()).toEqual([
      'bankAccount',
      'bankName',
      'companyName',
      'contactName',
      'contactPhone',
      'photos',
      'uscc',
    ]);
  });

  it.each([
    ['companyName', ' ', '请输入企业名称'],
    ['contactName', '', '请输入联系人姓名'],
    ['bankName', '  ', '请输入开户银行'],
  ] as const)('%s 空白 → 报错', (key, value, msg) => {
    const errs = validateMerchantForm({ ...VALID, [key]: value });
    expect(errs[key]).toBe(msg);
  });

  it.each([
    ['91440300MA5ABC123', '少一位'],
    ['91440300ma5abc1234', '小写非法'],
    ['91440300MA5ABC12345', '多一位'],
  ] as const)('uscc=%s (%s) → 报错', (uscc) => {
    expect(validateMerchantForm({ ...VALID, uscc }).uscc).toBe('统一社会信用代码须为18位数字或大写字母');
  });

  it.each([
    ['1380013800', '10位'],
    ['23800138000', '非1开头'],
    ['138001380001', '12位'],
    ['abc', '非数字'],
  ] as const)('contactPhone=%s (%s) → 报错', (phone) => {
    expect(validateMerchantForm({ ...VALID, contactPhone: phone }).contactPhone).toBe('请输入11位手机号');
  });

  it.each([
    ['12345678', '8位'],
    ['1234567890123456789012345678901', '31位'],
    ['AB123456', '含字母'],
  ] as const)('bankAccount=%s (%s) → 报错', (acc) => {
    expect(validateMerchantForm({ ...VALID, bankAccount: acc }).bankAccount).toBe('结算账号须为9-30位数字');
  });

  it('证照缺一即报 photos 错误', () => {
    const photos = { ...VALID.photos, license: null };
    expect(validateMerchantForm({ ...VALID, photos }).photos).toBe('请补齐全部证件照');
  });

  it('首尾空格不干扰合法性 (trim 后校验)', () => {
    const padded = {
      ...VALID,
      companyName: '  测试能源有限公司  ',
      uscc: ' 91440300MA5ABC1234 ',
      contactPhone: ' 13800138000 ',
    };
    expect(Object.keys(validateMerchantForm(padded))).toHaveLength(0);
  });
});

describe('字段/槽位定义', () => {
  it('6 文本字段 + 4 证照槽位, testID 不碰撞', () => {
    expect(MERCHANT_TEXT_FIELDS).toHaveLength(6);
    expect(MERCHANT_PHOTO_SLOTS).toHaveLength(4);
    const ids = [
      ...MERCHANT_TEXT_FIELDS.map((f) => f.testID),
      ...MERCHANT_PHOTO_SLOTS.map((s) => s.testID),
    ];
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('EMPTY_MERCHANT_FORM 证照槽全 null', () => {
    expect(Object.values(EMPTY_MERCHANT_FORM.photos).every((v) => v === null)).toBe(true);
  });
});

describe('pickMockPhotoUri', () => {
  it('按槽位生成占位 URI', () => {
    expect(pickMockPhotoUri('license')).toBe('file://mock-kyc/license.jpg');
    expect(pickMockPhotoUri('bankCard')).toBe('file://mock-kyc/bankCard.jpg');
  });
});
