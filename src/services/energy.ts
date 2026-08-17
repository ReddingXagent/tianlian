import { ApiResponse, EnergySummary } from '../types';
import api from './client';

// =====================
// 能源概览 API (GET /energy/summary)
// =====================
export const energyApi = {
  getSummary(): Promise<ApiResponse<EnergySummary>> {
    return api.get('/energy/summary').then((res) => {
      const d = res.data?.data as Record<string, unknown> | undefined;
      if (!d) {return res.data;}
      return {
        ...res.data,
        data: {
          period: (d.period as string) ?? '',
          days: (d.days as number) ?? 0,
          pvGeneration: (d.pv_generation as number) ?? 0,
          chargingAmount: (d.charging_amount as number) ?? 0,
          dischargeAmount: (d.discharge_amount as number) ?? 0,
          pvRevenue: (d.pv_revenue as number) ?? 0,
          chargingRevenue: (d.charging_revenue as number) ?? 0,
          dischargeRevenue: (d.discharge_revenue as number) ?? 0,
          totalRevenue: (d.total_revenue as number) ?? 0,
          yoy: {
            pvGenerationYoY: ((d.yoy as Record<string, unknown>)?.pv_generation_yoy as number) ?? 0,
            chargingAmountYoY: ((d.yoy as Record<string, unknown>)?.charging_amount_yoy as number) ?? 0,
            dischargeAmountYoY: ((d.yoy as Record<string, unknown>)?.discharge_amount_yoy as number) ?? 0,
            totalRevenueYoY: ((d.yoy as Record<string, unknown>)?.total_revenue_yoy as number) ?? 0,
          },
          priceInfo: {
            feedInTariff: ((d.price_info as Record<string, unknown>)?.feed_in_tariff as number) ?? 0,
            chargingPrice: ((d.price_info as Record<string, unknown>)?.charging_price as number) ?? 0,
            dischargePrice: ((d.price_info as Record<string, unknown>)?.discharge_price as number) ?? 0,
          },
        },
      };
    });
  },
};
