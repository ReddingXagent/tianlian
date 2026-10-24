/**
 * types/modules/merchant-audit.ts — 商户进件审核 (服务商特约商户 KYC) 领域类型
 * 卡 a8ca56aa ops-app 审核侧: 与 station-app 提交侧共用同一契约形状
 * (跨端字段名一致, 云端契约落地后仅 services/api-modules/merchant-audit.ts 映射层跟进)
 */

/** 进件状态机: pending(待审核) → audit(审核中) → approved(已通过) / rejected(已驳回, 可重提) */
export type MerchantApplicationStatus = 'pending' | 'audit' | 'rejected' | 'approved';

/** 状态展示文案 (领域常量, 提交/审核两端共享同一文案表) */
export const MERCHANT_STATUS_LABEL: Record<MerchantApplicationStatus, string> = {
  pending: '待审核',
  audit: '审核中',
  rejected: '已驳回',
  approved: '已通过',
};

export function merchantStatusLabel(status: MerchantApplicationStatus): string {
  return MERCHANT_STATUS_LABEL[status];
}

/** 证件照槽位 (uri; mock 通道为 file://mock-kyc/* 占位) */
export interface MerchantPhotoUris {
  /** 营业执照 */
  license: string | null;
  /** 身份证正面 */
  idCardFront: string | null;
  /** 身份证反面 */
  idCardBack: string | null;
  /** 银行卡照片 */
  bankCard: string | null;
}

/** 进件申请表单 (运营商提交: 证照 + 结算账户) */
export interface MerchantApplicationFormInput {
  companyName: string;
  /** 统一社会信用代码 (18位) */
  uscc: string;
  contactName: string;
  contactPhone: string;
  bankName: string;
  bankAccount: string;
  photos: MerchantPhotoUris;
}

/** 进件申请单 (审核侧列表/详情/操作对象) */
export interface MerchantApplication {
  id: number;
  status: MerchantApplicationStatus;
  submittedAt: string;
  updatedAt: string;
  /** 驳回原因 (仅 rejected 非空) */
  rejectReason: string | null;
  form: MerchantApplicationFormInput;
}

/** 审核列表 (云端契约未定, 先整页拉取, 分页字段映射层容忍缺省) */
export interface MerchantApplicationList {
  items: MerchantApplication[];
  total: number;
}
