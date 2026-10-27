/**
 * utils/merchant-kyc.ts — 商户进件表单纯函数域 (卡 a8ca56aa)
 * 字段定义/校验/mock选图均为纯函数, 与 UI 解耦便于穷举测试
 */
import type { MerchantApplicationFormInput, MerchantPhotoUris } from '../types';

export type MerchantTextFieldKey =
  | 'companyName'
  | 'uscc'
  | 'contactName'
  | 'contactPhone'
  | 'bankName'
  | 'bankAccount';

export type MerchantPhotoSlotKey = keyof MerchantPhotoUris;

export interface MerchantTextFieldDef {
  key: MerchantTextFieldKey;
  label: string;
  placeholder: string;
  testID: string;
}

export interface MerchantPhotoSlotDef {
  key: MerchantPhotoSlotKey;
  label: string;
  testID: string;
}

export const MERCHANT_TEXT_FIELDS: readonly MerchantTextFieldDef[] = [
  { key: 'companyName', label: '企业名称', placeholder: '与营业执照一致', testID: 'kyc-field-company' },
  { key: 'uscc', label: '统一社会信用代码', placeholder: '18位数字或大写字母', testID: 'kyc-field-uscc' },
  { key: 'contactName', label: '联系人', placeholder: '经办人姓名', testID: 'kyc-field-contact' },
  { key: 'contactPhone', label: '联系电话', placeholder: '11位手机号', testID: 'kyc-field-phone' },
  { key: 'bankName', label: '开户银行', placeholder: '如: 工商银行深圳分行', testID: 'kyc-field-bank-name' },
  { key: 'bankAccount', label: '结算账号', placeholder: '对公账户9-30位数字', testID: 'kyc-field-bank-account' },
];

export const MERCHANT_PHOTO_SLOTS: readonly MerchantPhotoSlotDef[] = [
  { key: 'license', label: '营业执照', testID: 'kyc-photo-license' },
  { key: 'idCardFront', label: '身份证正面', testID: 'kyc-photo-idfront' },
  { key: 'idCardBack', label: '身份证反面', testID: 'kyc-photo-idback' },
  { key: 'bankCard', label: '银行卡照片', testID: 'kyc-photo-bankcard' },
];

export const EMPTY_MERCHANT_PHOTOS: MerchantPhotoUris = {
  license: null,
  idCardFront: null,
  idCardBack: null,
  bankCard: null,
};

export const EMPTY_MERCHANT_FORM: MerchantApplicationFormInput = {
  companyName: '',
  uscc: '',
  contactName: '',
  contactPhone: '',
  bankName: '',
  bankAccount: '',
  photos: EMPTY_MERCHANT_PHOTOS,
};

export type MerchantFormErrors = Partial<Record<keyof MerchantApplicationFormInput, string>>;

const USCC_RE = /^[0-9A-Z]{18}$/;
const PHONE_RE = /^1\d{10}$/;
const BANK_ACCOUNT_RE = /^\d{9,30}$/;

/** 表单校验: 返回错误映射, 空对象即通过 (trim 后校验, 提交侧同样 trim) */
export function validateMerchantForm(input: MerchantApplicationFormInput): MerchantFormErrors {
  const errors: MerchantFormErrors = {};
  if (!input.companyName.trim()) errors.companyName = '请输入企业名称';
  if (!USCC_RE.test(input.uscc.trim())) errors.uscc = '统一社会信用代码须为18位数字或大写字母';
  if (!input.contactName.trim()) errors.contactName = '请输入联系人姓名';
  if (!PHONE_RE.test(input.contactPhone.trim())) errors.contactPhone = '请输入11位手机号';
  if (!input.bankName.trim()) errors.bankName = '请输入开户银行';
  if (!BANK_ACCOUNT_RE.test(input.bankAccount.trim())) errors.bankAccount = '结算账号须为9-30位数字';
  for (const slot of MERCHANT_PHOTO_SLOTS) {
    if (!input.photos[slot.key]) {
      errors.photos = '请补齐全部证件照';
      break;
    }
  }
  return errors;
}

/** mock 选图: 未引入原生选图依赖前统一发占位 URI (真机选图随 real 模式接入) */
export function pickMockPhotoUri(slot: MerchantPhotoSlotKey): string {
  return `file://mock-kyc/${slot}.jpg`;
}
