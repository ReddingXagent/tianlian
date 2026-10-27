import { ApiResponse, EnergySummary } from '../types';
import api from './client';
import { Raw, num, str } from './mappers';

// =====================
// 能源概览 API (GET /energy/summary)
// =====================
export const energyApi = {
  getSummary(): Promise<ApiResponse<EnergySummary>> {
    return api.get('/energy/summary').then((res) => {
      const d = res.data?.data as Raw | undefined;
      if (!d) {return res.data;}
      return {
        ...res.data,
        data: {
          period: str(d.period),
          days: num(d.days),
          pvGeneration: num(d.pv_generation),
          chargingAmount: num(d.charging_amount),
          dischargeAmount: num(d.discharge_amount),
          pvRevenue: num(d.pv_revenue),
          chargingRevenue: num(d.charging_revenue),
          dischargeRevenue: num(d.discharge_revenue),
          totalRevenue: num(d.total_revenue),
          yoy: {
            pvGenerationYoY: num((d.yoy as Raw | undefined)?.pv_generation_yoy),
            chargingAmountYoY: num((d.yoy as Raw | undefined)?.charging_amount_yoy),
            dischargeAmountYoY: num((d.yoy as Raw | undefined)?.discharge_amount_yoy),
            totalRevenueYoY: num((d.yoy as Raw | undefined)?.total_revenue_yoy),
          },
          priceInfo: {
            feedInTariff: num((d.price_info as Raw | undefined)?.feed_in_tariff),
            chargingPrice: num((d.price_info as Raw | undefined)?.charging_price),
            dischargePrice: num((d.price_info as Raw | undefined)?.discharge_price),
          },
        },
      };
    });
  },
};
