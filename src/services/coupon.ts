import { ApiResponse, Coupon, CouponStatus, PaginatedData } from '../types';
import api from './client';

// =====================
// 优惠券 API
// =====================
export const couponApi = {
  getList(params?: {
    status?: CouponStatus;
    page?: number;
    pageSize?: number;
  }): Promise<ApiResponse<PaginatedData<Coupon>>> {
    return api.get('/coupons', { params }).then((res) => res.data);
  },
  getAvailable(stationId?: number): Promise<ApiResponse<Coupon[]>> {
    return api.get('/coupons/available', { params: { stationId } }).then((res) => res.data);
  },
};
