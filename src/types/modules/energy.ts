/**
 * types/modules/energy.ts — 能源概览类型
 */
import type { EnergyYoY, EnergyPriceInfo } from '@tianlian/shared-types';
export { type EnergyYoY, type EnergyPriceInfo } from '@tianlian/shared-types';

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
