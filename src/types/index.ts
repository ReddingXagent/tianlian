import type { NavigatorScreenParams } from '@react-navigation/native';

// =====================
// 站点 (Station)
// =====================
export interface Station {
  id: number;
  name: string;
  address: string;
  status: StationStatus;
  latitude: number;
  longitude: number;
  distance?: number;         // 米
  pricePerKwh: number;       // 元/度
  serviceFee: number;        // 服务费
  totalConnectors: number;   // 充电枪总数
  availableConnectors: number; // 可用充电枪数
  chargingConnectors: number;  // 充电中枪数
  isOpen24h: boolean;
  openingHours?: string;
  rating: number;
  createdAt: string;
  updatedAt: string;
}

export type StationStatus = 'online' | 'offline' | 'maintenance';

// =====================
// 充电桩 (Charger/Connector)
// =====================
export interface Charger {
  id: number;
  stationId: number;
  name: string;
  code: string;
  type: ChargerType;
  status: ConnectorStatus;
  power: number;              // kW 额定功率
  pricePerKwh: number;        // 元/度
  serviceFee: number;         // 服务费
}

export type ChargerType = 'dc' | 'ac';
export type ConnectorStatus = 'idle' | 'charging' | 'offline' | 'fault';

// =====================
// 充电订单 (Order)
// =====================
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
  duration: number;            // 分钟
  energy: number;              // kWh 充电量
  power: number;               // kW 实时功率
  voltage: number;             // V 实时电压
  current: number;             // A 实时电流
  amount: number;              // 费用 元
  couponId?: number;
  couponDiscount: number;      // 优惠金额
  paymentStatus: PaymentStatus;
  paymentMethod?: PaymentMethod;
  createdAt: string;
  updatedAt: string;
}

export type OrderStatus = 'charging' | 'completed' | 'cancelled' | 'timeout';
export type PaymentStatus = 'unpaid' | 'paid' | 'refunding' | 'refunded';
export type PaymentMethod = 'wechat' | 'alipay' | 'balance';

// =====================
// 车辆 (Vehicle)
// =====================
export interface Vehicle {
  id: number;
  userId: number;
  plate: string;
  brand: string;
  model: string;
  color: string;
  vin: string;
  isDefault: boolean;
  createdAt: string;
}

// =====================
// 优惠券 (Coupon)
// =====================
export interface Coupon {
  id: number;
  userId: number;
  title: string;
  description: string;
  type: CouponType;
  value: number;              // 面值 元
  condition: string;          // 使用条件说明
  status: CouponStatus;
  startAt: string;
  expireAt: string;
  usedAt?: string;
  createdAt: string;
}

export type CouponType = 'amount' | 'discount' | 'free_hour';
export type CouponStatus = 'unused' | 'used' | 'expired';

// =====================
// 用户 (User)
// =====================
export interface User {
  id: number;
  phone: string;
  nickname: string;
  avatar?: string;
  balance: number;             // 钱包余额 元
  createdAt: string;
  updatedAt: string;
}

// =====================
// 钱包 (Wallet)
// =====================
export interface WalletRecord {
  id: number;
  userId: number;
  type: WalletRecordType;
  amount: number;
  balance: number;
  description: string;
  createdAt: string;
}

export type WalletRecordType = 'recharge' | 'consume' | 'refund' | 'withdraw';

// =====================
// 通用API响应
// =====================
export interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
}

export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

// =====================
// 认证
// =====================
export interface LoginRequest {
  phone: string;
  code?: string;
  password?: string;
}

export interface SendCodeRequest {
  phone: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

// =====================
// 扫码
// =====================
export interface ScanResult {
  id: number;
  type: 'charger';
  code: string;
  name: string;
  stationId: number;
  stationName: string;
  power: number;
  pricePerKwh: number;
  serviceFee: number;
  status: ConnectorStatus;
}

// =====================
// 充电
// =====================
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
  power: number;         // kW 实时功率
  voltage: number;       // V
  current: number;       // A
  energy: number;        // kWh 已充电量
  duration: number;      // 分钟
  amount: number;        // 当前费用
  startTime: string;
}

// =====================
// 支付
// =====================
export interface PaymentRequest {
  orderId: number;
  method: PaymentMethod;
  couponId?: number;
}

export interface PaymentResult {
  success: boolean;
  message: string;
  amount: number;
  paidAmount: number;
  tradeNo?: string;
}

// =====================
// 导航参数
// =====================
export type RootStackParamList = {
  Auth: undefined;
  Main: NavigatorScreenParams<MainTabParamList> | undefined;
  StationDetail: { stationId: number };
  Charging: { orderId: number };
  OrderDetail: { orderId: number };
  Payment: { orderId: number; amount: number };
  Vehicle: undefined;
  Wallet: undefined;
  Coupon: undefined;
  Login: undefined;
};

export type AuthStackParamList = {
  Login: undefined;
};

export type MainTabParamList = {
  Home: undefined;
  Orders: undefined;
  Scan: undefined;
  Profile: undefined;
};

// =====================
// 搜索
// =====================
export interface StationQuery {
  keyword?: string;
  latitude?: number;
  longitude?: number;
  radius?: number;            // 搜索半径 米
  page?: number;
  pageSize?: number;
}

// =====================
// 统计数据
// =====================
export interface UserStats {
  totalOrders: number;
  totalEnergy: number;        // kWh
  totalAmount: number;        // 元
  totalDuration: number;      // 分钟
  couponCount: number;
}

// =====================
// 能源概览 (Energy Summary — GET /energy/summary)
// =====================
export interface EnergyYoY {
  pvGenerationYoY: number;
  chargingAmountYoY: number;
  dischargeAmountYoY: number;
  totalRevenueYoY: number;
}

export interface EnergyPriceInfo {
  feedInTariff: number;
  chargingPrice: number;
  dischargePrice: number;
}

export interface EnergySummary {
  period: string;
  days: number;
  pvGeneration: number;      // kWh 光伏发电量
  chargingAmount: number;     // kWh 充电量
  dischargeAmount: number;    // kWh 放电量
  pvRevenue: number;          // 元 光伏收入
  chargingRevenue: number;    // 元 充电收入
  dischargeRevenue: number;   // 元 放电收入
  totalRevenue: number;       // 元 总收入
  yoy: EnergyYoY;
  priceInfo: EnergyPriceInfo;
}