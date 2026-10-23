/**
 * services/merchant.ts — 商户进件 (服务商特约商户 KYC) 云端契约客户端
 * 卡 a8ca56aa: 契约未定稿, 默认走 merchant-source 的 mock 通道;
 * 云端 POST /business/merchant-applications (multipart) + GET /:id 落地后
 * 设 EXPO_PUBLIC_MERCHANT_KYC_MODE=real 即切换, 本文件即真实契约映射层.
 */
import type { ApiResponse, MerchantApplication, MerchantApplicationFormInput, MerchantApplicationStatus } from '../types';
import api from './client';

/** 云端原始契约形态 (snake_case, 字段全可选容忍缺省) */
export interface RawMerchantApplication {
  id?: number;
  status?: string;
  submitted_at?: string;
  updated_at?: string;
  reject_reason?: string | null;
  company_name?: string;
  uscc?: string;
  contact_name?: string;
  contact_phone?: string;
  bank_name?: string;
  bank_account?: string;
  license_photo?: string | null;
  id_card_front_photo?: string | null;
  id_card_back_photo?: string | null;
  bank_card_photo?: string | null;
}

/** 后端状态词归一 (含别名), 未识别回落 pending */
const STATUS_NORMALIZE: Record<string, MerchantApplicationStatus> = {
  pending: 'pending',
  audit: 'audit',
  auditing: 'audit',
  reviewing: 'audit',
  rejected: 'rejected',
  approved: 'approved',
};

export const MERCHANT_STATUS_LABEL: Record<MerchantApplicationStatus, string> = {
  pending: '待审核',
  audit: '审核中',
  rejected: '已驳回',
  approved: '已通过',
};

export function merchantStatusLabel(status: MerchantApplicationStatus): string {
  return MERCHANT_STATUS_LABEL[status];
}

export function mapMerchantApplication(raw: RawMerchantApplication): MerchantApplication {
  return {
    id: raw.id ?? 0,
    status: STATUS_NORMALIZE[raw.status ?? ''] ?? 'pending',
    submittedAt: raw.submitted_at ?? '',
    updatedAt: raw.updated_at ?? '',
    rejectReason: raw.reject_reason ?? null,
    form: {
      companyName: raw.company_name ?? '',
      uscc: raw.uscc ?? '',
      contactName: raw.contact_name ?? '',
      contactPhone: raw.contact_phone ?? '',
      bankName: raw.bank_name ?? '',
      bankAccount: raw.bank_account ?? '',
      photos: {
        license: raw.license_photo ?? null,
        idCardFront: raw.id_card_front_photo ?? null,
        idCardBack: raw.id_card_back_photo ?? null,
        bankCard: raw.bank_card_photo ?? null,
      },
    },
  };
}

const PHOTO_PART_NAMES: readonly { field: keyof MerchantApplicationFormInput['photos']; part: string; file: string }[] = [
  { field: 'license', part: 'license_photo', file: 'license.jpg' },
  { field: 'idCardFront', part: 'id_card_front_photo', file: 'id-card-front.jpg' },
  { field: 'idCardBack', part: 'id_card_back_photo', file: 'id-card-back.jpg' },
  { field: 'bankCard', part: 'bank_card_photo', file: 'bank-card.jpg' },
];

/** multipart 组装: 表单字段 snake_case + 证件照文件部件 (RN FormData 原生 {uri,name,type}) */
export function buildMerchantFormData(input: MerchantApplicationFormInput): FormData {
  const fd = new FormData();
  fd.append('company_name', input.companyName.trim());
  fd.append('uscc', input.uscc.trim());
  fd.append('contact_name', input.contactName.trim());
  fd.append('contact_phone', input.contactPhone.trim());
  fd.append('bank_name', input.bankName.trim());
  fd.append('bank_account', input.bankAccount.trim());
  for (const p of PHOTO_PART_NAMES) {
    const uri = input.photos[p.field];
    if (uri) {
      // jest 环境为 undici FormData (对象部件会字符串化), 契约测试以字段名存在性为准
      fd.append(p.part, { uri, name: p.file, type: 'image/jpeg' } as unknown as Blob);
    }
  }
  return fd;
}

export const merchantApi = {
  /** 提交进件申请 (multipart: 证照 + 表单) */
  submitApplication(input: MerchantApplicationFormInput): Promise<ApiResponse<MerchantApplication>> {
    return api
      .post('/business/merchant-applications', buildMerchantFormData(input), {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((res) => ({
        ...res.data,
        data: mapMerchantApplication((res.data?.data ?? {}) as RawMerchantApplication),
      }));
  },
  /** 查询进件状态 */
  getApplication(id: number): Promise<ApiResponse<MerchantApplication>> {
    return api
      .get(`/business/merchant-applications/${id}`)
      .then((res) => ({
        ...res.data,
        data: mapMerchantApplication((res.data?.data ?? {}) as RawMerchantApplication),
      }));
  },
};
