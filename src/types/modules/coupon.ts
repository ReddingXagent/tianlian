/**
 * types/modules/coupon.ts — 优惠券类型
 */
export type CouponType = 'amount' | 'discount' | 'free_hour';
export type CouponStatus = 'unused' | 'used' | 'expired';

export interface Coupon {
  id: number;
  userId: number;
  title: string;
  description: string;
  type: CouponType;
  value: number;
  condition: string;
  status: CouponStatus;
  startAt: string;
  expireAt: string;
  usedAt?: string;
  createdAt: string;
}
