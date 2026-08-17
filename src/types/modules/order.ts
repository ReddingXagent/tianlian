/**
 * types/modules/order.ts — 充电订单/支付类型
 */
export type OrderStatus = 'charging' | 'completed' | 'cancelled' | 'timeout';
export type PaymentStatus = 'unpaid' | 'paid' | 'refunding' | 'refunded';
export type PaymentMethod = 'wechat' | 'alipay' | 'balance';

export interface Order {
  id: number;
  orderNo: string;
  userId: number;
  stationId: number;
  stationName: string;
  chargerId: number;
  chargerName: string;
  vehicleId?: number;
  vehiclePlate?: string;
  status: OrderStatus;
  startTime: string;
  endTime?: string;
  duration: number;
  energy: number;
  power: number;
  voltage: number;
  current: number;
  amount: number;
  couponId?: number;
  couponDiscount: number;
  paymentStatus: PaymentStatus;
  paymentMethod?: PaymentMethod;
  createdAt: string;
  updatedAt: string;
}

export interface StartChargingRequest {
  chargerId: number;
  vehicleId?: number;
  couponId?: number;
}

export interface ChargingStatus {
  orderId: number;
  orderNo: string;
  chargerName: string;
  stationName: string;
  status: OrderStatus;
  power: number;
  voltage: number;
  current: number;
  energy: number;
  duration: number;
  amount: number;
  startTime: string;
}

export interface PaymentRequest {
  orderId: number;
  method: PaymentMethod;
  couponId?: number;
}

// 微信服务商支付 (WeChat Service Provider Payment)
export interface WeChatServiceProviderPayment {
  spMchid: string;
  subMchid: string;
  timeStamp: string;
  nonceStr: string;
  package: string;
  signType: string;
  paySign: string;
}

export interface PaymentResult {
  success: boolean;
  message: string;
  amount: number;
  paidAmount: number;
  tradeNo?: string;
  payParams?: WeChatServiceProviderPayment;
}
