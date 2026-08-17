/**
 * types/modules/energy.ts — 能源概览类型
 */
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
  pvGeneration: number;
  chargingAmount: number;
  dischargeAmount: number;
  pvRevenue: number;
  chargingRevenue: number;
  dischargeRevenue: number;
  totalRevenue: number;
  yoy: EnergyYoY;
  priceInfo: EnergyPriceInfo;
}
