/**
 * api-modules/merchant-audit.ts — 商户进件审核 (KYC) 云端契约客户端
 * 卡 a8ca56aa ops-app 审核侧: 契约未定稿, 默认走 merchant-audit-source 的 mock 通道;
 * 云端 GET /business/merchant-applications (列表) + POST /:id/approve|reject 落地后
 * 设 EXPO_PUBLIC_MERCHANT_KYC_MODE=real 即切换 (与 station-app 提交侧同一开关), 本文件即真实契约映射层.
 */
import api from './client';
import { MERCHANT_STATUS_LABEL, merchantStatusLabel } from '../../types';
import type {
  ApiResponse,
  MerchantApplication,
  MerchantApplicationList,
  MerchantApplicationStatus,
} from '../../types';

// 领域常量已上提至 types/modules/merchant-audit (screen 直连 types, 避免拉 client 原生依赖)
export { MERCHANT_STATUS_LABEL, merchantStatusLabel };

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

/** 后端状态词归一 (含别名), 未识别回落 pending (与 station-app 提交侧同表) */
const STATUS_NORMALIZE: Record<string, MerchantApplicationStatus> = {
  pending: 'pending',
  audit: 'audit',
  auditing: 'audit',
  reviewing: 'audit',
  rejected: 'rejected',
  approved: 'approved',
};

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

/** 列表原始形态: { data: { items: [...] } } 或裸数组双容忍 */
export function mapMerchantApplicationList(raw: unknown): MerchantApplicationList {
  const envelope = (raw ?? {}) as Record<string, unknown>;
  const d = (envelope.data ?? envelope) as Record<string, unknown>;
  const rawItems = (d.items as RawMerchantApplication[] | undefined) ?? [];
  const items = rawItems.map(mapMerchantApplication);
  return { items, total: (d.total as number | undefined) ?? items.length };
}

export const merchantAuditApi = {
  /** GET /business/merchant-applications — 审核列表 (可选状态过滤) */
  getList(params?: {
    status?: MerchantApplicationStatus;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<MerchantApplicationList>> {
    return api
      .get('/business/merchant-applications', {
        params: {
          ...(params?.status !== undefined && { status: params.status }),
          ...(params?.page !== undefined && { page: params.page }),
          ...(params?.pageSize !== undefined && { page_size: params.pageSize }),
        },
      })
      .then((res) => ({
        ...res.data,
        data: mapMerchantApplicationList(res.data),
      }));
  },

  /** GET /business/merchant-applications/:id — 申请详情 */
  getApplication(id: number): Promise<ApiResponse<MerchantApplication>> {
    return api
      .get(`/business/merchant-applications/${id}`)
      .then((res) => ({
        ...res.data,
        data: mapMerchantApplication((res.data?.data ?? {}) as RawMerchantApplication),
      }));
  },

  /** POST /business/merchant-applications/:id/approve — 批准进件 */
  approve(id: number): Promise<ApiResponse<MerchantApplication>> {
    return api
      .post(`/business/merchant-applications/${id}/approve`)
      .then((res) => ({
        ...res.data,
        data: mapMerchantApplication((res.data?.data ?? {}) as RawMerchantApplication),
      }));
  },

  /** POST /business/merchant-applications/:id/reject — 驳回进件 (需原因) */
  reject(id: number, reason: string): Promise<ApiResponse<MerchantApplication>> {
    return api
      .post(`/business/merchant-applications/${id}/reject`, {
        reject_reason: reason,
      })
      .then((res) => ({
        ...res.data,
        data: mapMerchantApplication((res.data?.data ?? {}) as RawMerchantApplication),
      }));
  },
};
