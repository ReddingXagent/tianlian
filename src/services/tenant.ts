import { ApiResponse, TenantBranding } from '../types';
import api from './client';

// =====================
// 租户品牌 API (GET /tenants/{id}/branding)
// =====================
export const tenantApi = {
  getBranding(tenantId: string): Promise<ApiResponse<TenantBranding>> {
    return api.get(`/tenants/${tenantId}/branding`).then((res) => {
      const d = res.data?.data as Record<string, unknown> | undefined;
      if (!d) {return res.data;}
      return {
        ...res.data,
        data: {
          tenantId: String(d.tenant_id ?? d.tenantId ?? tenantId),
          operatorName: (d.operator_name as string) ?? (d.operatorName as string) ?? '天链',
          logoUrl: (d.logo_url as string | undefined) ?? (d.logoUrl as string | undefined),
          themeColor: (d.theme_color as string) ?? (d.themeColor as string) ?? '#00A86B',
          source: ((d.source as string) ?? 'default') as 'default' | 'operator' | 'custom',
        },
      };
    });
  },
};
