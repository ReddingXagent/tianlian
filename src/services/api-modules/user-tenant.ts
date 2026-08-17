/**
 * api-modules/user-tenant.ts — 用户/租户/站点/团队 API
 * 从 extended.ts 拆分 (F1361 维度22 领域细分)
 */
import api from './client';
import {
  ApiResponse,
  UserDetail,
  UserCreate,
  PaginatedData,
  Tenant,
  Station,
  StationCreate,
  StationBranding,
  Team,
  TeamUpdate,
  TeamCreate,
  TeamMember,
} from '../../types';

// =====================
export const userApi = {
  /** GET /users/{id} — 用户详情 */
  getDetail(id: number): Promise<ApiResponse<UserDetail>> {
    return api.get(`/users/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      return {
        ...raw,
        data: {
          id: (d.id as number) ?? 0,
          username: (d.username as string) ?? '',
          realName: (d.real_name as string) ?? '',
          phone: (d.phone as string | null) ?? null,
          role: (d.role as string) ?? '',
          level: (d.level as string) ?? '',
          teamId: (d.team_id as number | null) ?? null,
          teamName: (d.team_name as string | null) ?? null,
          status: (d.status as string) ?? '',
          lastLogin: (d.last_login as string) ?? '',
          createdAt: (d.created_at as string) ?? '',
          updatedAt: (d.updated_at as string) ?? '',
        },
      };
    });
  },

  /** POST /users — 创建用户 */
  create(body: UserCreate): Promise<ApiResponse<UserDetail>> {
    const payload: Record<string, unknown> = { username: body.username };
    if (body.password != null) payload.password = body.password;
    if (body.realName != null) payload.real_name = body.realName;
    if (body.phone != null) payload.phone = body.phone;
    if (body.role != null) payload.role = body.role;
    if (body.level != null) payload.level = body.level;
    if (body.teamId != null) payload.team_id = body.teamId;
    return api.post('/users', payload).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      if (raw.data == null) return { ...raw, data: null as unknown as UserDetail };
      const d = raw.data as Record<string, unknown>;
      return {
        ...raw,
        data: {
          id: (d.id as number) ?? 0,
          username: (d.username as string) ?? '',
          realName: (d.real_name as string) ?? '',
          phone: (d.phone as string | null) ?? null,
          role: (d.role as string) ?? '',
          level: (d.level as string) ?? '',
          teamId: (d.team_id as number | null) ?? null,
          teamName: (d.team_name as string | null) ?? null,
          status: (d.status as string) ?? '',
          lastLogin: (d.last_login as string) ?? '',
          createdAt: (d.created_at as string) ?? '',
          updatedAt: (d.updated_at as string) ?? '',
        },
      };
    });
  },
};

// =====================
// 报告 API (GET /reports/summary)

// =====================
// 租户管理 API (/tenants)
// =====================
export interface TenantCreate {
  name: string;
  code: string;
}

export const tenantListApi = {
  /** GET /tenants — 租户列表 */
  getList(): Promise<ApiResponse<PaginatedData<Tenant>>> {
    return api.get('/tenants').then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = (d.items as Record<string, unknown>[]) ?? [];
      return {
        ...raw,
        data: {
          items: items.map((item): Tenant => ({
            id: item.id as number,
            name: (item.name as string) ?? '',
            code: (item.code as string) ?? '',
            status: (item.status as string) ?? 'active',
            createdAt: (item.created_at as string) ?? '',
            updatedAt: (item.updated_at as string) ?? '',
          })),
          total: (d.total as number) ?? 0,
          page: (d.page as number) ?? 1,
          pageSize: (d.page_size as number) ?? 20,
        },
      };
    });
  },

  /** POST /tenants — 创建租户 */
  create(body: TenantCreate): Promise<ApiResponse<Tenant>> {
    return api
      .post('/tenants', {
        name: body.name,
        code: body.code,
      })
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            code: (it.code as string) ?? '',
            status: (it.status as string) ?? 'active',
            createdAt: (it.created_at as string) ?? '',
            updatedAt: (it.updated_at as string) ?? '',
          },
        };
      });
  },

  /** DELETE /tenants/{id} — 删除租户 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/tenants/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      return { ...raw, data: null };
    });
  },
};


// =====================
// 站点 API (GET /stations, GET /stations/{id})
// =====================
function mapStation(raw: Record<string, unknown>): Station {
  const brandingRaw = (raw.branding ?? null) as Record<string, unknown> | null;
  let branding: StationBranding | null = null;
  if (brandingRaw) {
    branding = {
      operatorName: (brandingRaw.operator_name as string) ?? '',
      logoUrl: (brandingRaw.logo_url as string) ?? '',
      servicePhone: (brandingRaw.service_phone as string) ?? '',
      themeColor: (brandingRaw.theme_color as string) ?? '#00A86B',
      source: (brandingRaw.source as string) ?? 'default',
    };
  }
  return {
    id: (raw.id as number) ?? 0,
    name: (raw.name as string) ?? '',
    code: (raw.code as string) ?? '',
    province: (raw.province as string) ?? '',
    city: (raw.city as string) ?? '',
    district: (raw.district as string) ?? '',
    address: (raw.address as string) ?? '',
    lat: (raw.lat as number) ?? 0,
    lon: (raw.lon as number) ?? 0,
    status: (raw.status as Station['status']) ?? 'normal',
    stationType: (raw.station_type as string | null) ?? null,
    operatorId: (raw.operator_id as number | null) ?? null,
    operatorName: (raw.operator_name as string | null) ?? null,
    teamId: (raw.team_id as number | null) ?? null,
    totalPower: (raw.total_power as number) ?? 0,
    totalDevices: (raw.total_devices as number) ?? 0,
    gunCount: (raw.gun_count as number) ?? 0,
    venueType: (raw.venue_type as string | null) ?? null,
    totalCost: (raw.total_cost as number | null) ?? null,
    parkingSpots: (raw.parking_spots as number | null) ?? null,
    healthScore: (raw.health_score as number) ?? 0,
    branding,
    createdAt: (raw.created_at as string) ?? '',
    updatedAt: (raw.updated_at as string | null) ?? null,
  };
}

export const stationApi = {
  /** GET /stations — 站点列表 (分页) */
  getList(params?: {
    page?: number;
    pageSize?: number;
    status?: string;
    keyword?: string;
  }): Promise<ApiResponse<PaginatedData<Station>>> {
    const query: Record<string, string> = {};
    if (params?.page != null) query.page = String(params.page);
    if (params?.pageSize != null) query.page_size = String(params.pageSize);
    if (params?.status != null) query.status = params.status;
    if (params?.keyword != null) query.keyword = params.keyword;
    return api.get('/stations', { params: query }).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      const d = (raw.data ?? {}) as Record<string, unknown>;
      const items = ((d.items ?? []) as Record<string, unknown>[]).map(mapStation);
      return {
        ...raw,
        data: {
          items,
          total: (d.total as number) ?? items.length,
          page: (d.page as number) ?? (params?.page ?? 1),
          pageSize: (d.page_size as number) ?? (params?.pageSize ?? 20),
        },
      };
    });
  },

  /** GET /stations/{id} — 站点详情 */
  getDetail(id: number): Promise<ApiResponse<Station>> {
    return api.get(`/stations/${id}`).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      return { ...raw, data: mapStation((raw.data ?? {}) as Record<string, unknown>) };
    });
  },

  /** POST /stations — 创建站点 */
  create(body: StationCreate): Promise<ApiResponse<Station>> {
    const payload: Record<string, unknown> = { name: body.name };
    if (body.code != null) payload.code = body.code;
    if (body.province != null) payload.province = body.province;
    if (body.city != null) payload.city = body.city;
    if (body.district != null) payload.district = body.district;
    if (body.address != null) payload.address = body.address;
    if (body.lat != null) payload.lat = body.lat;
    if (body.lon != null) payload.lon = body.lon;
    if (body.stationType != null) payload.station_type = body.stationType;
    if (body.operatorId != null) payload.operator_id = body.operatorId;
    if (body.teamId != null) payload.team_id = body.teamId;
    if (body.totalPower != null) payload.total_power = body.totalPower;
    if (body.venueType != null) payload.venue_type = body.venueType;
    if (body.totalCost != null) payload.total_cost = body.totalCost;
    if (body.parkingSpots != null) payload.parking_spots = body.parkingSpots;
    return api.post('/stations', payload).then((res) => {
      const raw = res.data as ApiResponse<Record<string, unknown>>;
      return { ...raw, data: mapStation((raw.data ?? {}) as Record<string, unknown>) };
    });
  },
};


// =====================
// 团队 API (teams — /teams)
// =====================
export const teamApi = {
  /** GET /teams — 团队列表 */
  getList(params?: { page?: number; page_size?: number }): Promise<ApiResponse<PaginatedData<Team>>> {
    const query = params ? `?page=${params.page ?? 1}&page_size=${params.page_size ?? 20}` : '';
    return api
      .get(`/teams${query}`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const d = (raw.data ?? {}) as Record<string, unknown>;
        const items = ((d.items as Record<string, unknown>[]) ?? []).map((it) => ({
          id: (it.id as number) ?? 0,
          name: (it.name as string) ?? '',
          code: (it.code as string | null) ?? null,
          leaderId: (it.leader_id as number | null) ?? null,
          leaderName: (it.leader_name as string | null) ?? null,
          description: (it.description as string | null) ?? null,
          memberCount: (it.member_count as number) ?? 0,
          stationCount: (it.station_count as number) ?? 0,
          status: (it.status as string) ?? 'active',
          createdAt: (it.created_at as string | null) ?? null,
        }));
        return {
          ...raw,
          data: {
            items,
            total: (d.total as number) ?? items.length,
            page: (d.page as number) ?? (params?.page ?? 1),
            pageSize: (d.page_size as number) ?? (params?.page_size ?? 20),
          },
        };
      });
  },

  /** GET /teams/{id} — 团队详情 */
  getDetail(id: number): Promise<ApiResponse<Team>> {
    return api
      .get(`/teams/${id}`)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            code: (it.code as string | null) ?? null,
            leaderId: (it.leader_id as number | null) ?? null,
            leaderName: (it.leader_name as string | null) ?? null,
            description: (it.description as string | null) ?? null,
            memberCount: (it.member_count as number) ?? 0,
            stationCount: (it.station_count as number) ?? 0,
            status: (it.status as string) ?? 'active',
            createdAt: (it.created_at as string | null) ?? null,
          },
        };
      });
  },

  /** PUT /teams/{id} — 更新团队 */
  update(id: number, body: TeamUpdate): Promise<ApiResponse<Team>> {
    // camel → snake for request body
    const payload: Record<string, unknown> = {};
    if (body.name !== undefined) payload.name = body.name;
    if (body.description !== undefined) payload.description = body.description;
    if (body.leaderId !== undefined) payload.leader_id = body.leaderId;
    if (body.status !== undefined) payload.status = body.status;
    return api
      .put(`/teams/${id}`, payload)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            code: (it.code as string | null) ?? null,
            leaderId: (it.leader_id as number | null) ?? null,
            leaderName: (it.leader_name as string | null) ?? null,
            description: (it.description as string | null) ?? null,
            memberCount: (it.member_count as number) ?? 0,
            stationCount: (it.station_count as number) ?? 0,
            status: (it.status as string) ?? 'active',
            createdAt: (it.created_at as string | null) ?? null,
          },
        };
      });
  },

  /** POST /teams — 创建团队 */
  create(body: TeamCreate): Promise<ApiResponse<Team>> {
    const payload: Record<string, unknown> = { name: body.name };
    if (body.code !== undefined) payload.code = body.code;
    if (body.description !== undefined) payload.description = body.description;

    return api
      .post('/teams', payload)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            name: (it.name as string) ?? '',
            code: (it.code as string | null) ?? null,
            leaderId: (it.leader_id as number | null) ?? null,
            leaderName: (it.leader_name as string | null) ?? null,
            description: (it.description as string | null) ?? null,
            memberCount: (it.member_count as number) ?? 0,
            stationCount: (it.station_count as number) ?? 0,
            status: (it.status as string) ?? 'active',
            createdAt: (it.created_at as string | null) ?? null,
          },
        };
      });
  },

  /** DELETE /teams/{id} — 删除团队 */
  delete(id: number): Promise<ApiResponse<null>> {
    return api.delete(`/teams/${id}`).then((res) => {
      return res.data as ApiResponse<null>;
    });
  },

  /** POST /teams/{id}/members — 添加团队成员 */
  addMember(teamId: number, userId: number, role?: string): Promise<ApiResponse<TeamMember>> {
    const payload: Record<string, unknown> = { user_id: userId };
    if (role) payload.role = role;
    return api
      .post(`/teams/${teamId}/members`, payload)
      .then((res) => {
        const raw = res.data as ApiResponse<Record<string, unknown>>;
        const it = (raw.data ?? {}) as Record<string, unknown>;
        return {
          ...raw,
          data: {
            id: (it.id as number) ?? 0,
            userId: (it.user_id as number) ?? 0,
            username: (it.username as string) ?? '',
            realName: (it.real_name as string) ?? null,
            teamId: (it.team_id as number) ?? 0,
            role: (it.role as string) ?? 'member',
            level: (it.level as string) ?? null,
            phone: (it.phone as string) ?? null,
            status: (it.status as string) ?? 'active',
            joinDate: (it.join_date as string) ?? null,
          },
        };
      });
  },

  /** DELETE /teams/{id}/members/{userId} — 移除团队成员 */
  removeMember(teamId: number, userId: number): Promise<ApiResponse<null>> {
    return api.delete(`/teams/${teamId}/members/${userId}`).then((res) => {
      return res.data as ApiResponse<null>;
    });
  },
};
