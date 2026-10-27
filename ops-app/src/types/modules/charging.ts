/**
 * types/modules/charging.ts — 充电订单/定价类型
 */
export type ChargingPaymentStatus = 'unpaid' | 'paid' | 'refunded' | 'refunding';

export type ChargingOrderStatus =
  | 'pending'
  | 'charging'
  | 'completed'
  | 'cancelled'
  | 'faulted';

export interface ChargingOrder {
  id: number;
  orderNo: string;
  stationId: number;
  deviceId: number;
  userId: number;
  userType: string | null;
  vehicleId: string | null;
  plateNumber: string | null;
  startTime: string | null;
  endTime: string | null;
  durationMinutes: number;
  startSoc: number | null;
  endSoc: number | null;
  startMeter: number | null;
  endMeter: number | null;
  stopReason: string | null;
  chargedKwh: number;
  electricityFee: number;
  serviceFee: number;
  parkingFee: number;
  idlePenalty: number;
  reservationFee: number;
  totalAmount: number;
  discountAmount: number;
  paidAmount: number;
  paymentStatus: ChargingPaymentStatus;
  orderStatus: ChargingOrderStatus;
  paymentMethod: string | null;
  remark: string | null;
  createdAt: string;
  updatedAt: string;
}

// 定价规则 (PricingRule — from /pricing)
export interface PricingRule {
  id: number;
  name: string;
  periodType: string;
  startTime: string;
  endTime: string;
  energyPrice?: number;
  servicePrice?: number;
  powerLimit?: number;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}
