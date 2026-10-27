/**
 * 智能充电调度 — 共享类型
 *
 * 对应后端 Phase45: /api/v1/fleet/charging/schedule/*
 * (app/api/v1/charging_schedule.py, app/models/charging_schedule.py)
 *
 * 注意: 后端计划状态枚举为 planned/active/completed/cancelled
 *       (任务描述里的 draft 在后端不存在，统一用 planned)
 */

/** 计划状态 */
export type PlanStatus = 'planned' | 'active' | 'completed' | 'cancelled';

/** 充放电模式 */
export type ChargeMode = 'charge' | 'discharge' | 'idle';

/** 电价时段类型(峰/平/谷)；尖峰归入 peak 显示 */
export type PeriodType = 'peak' | 'flat' | 'valley' | null;

/** 调度条目 — 单车功率分配 */
export interface ScheduleEntry {
  id: number;
  plan_id?: number;
  vehicle_id: number;
  assigned_power_kw: number;
  /** ISO datetime; 仅 current/detail 接口返回，generate 返回的条目无此字段 */
  start_time?: string | null;
  end_time?: string | null;
  priority: number;
  soc_start?: number;
  soc_target?: number;
  charge_mode: ChargeMode;
  period_type?: PeriodType;
}

/** 调度计划 */
export interface SchedulePlan {
  id: number;
  enterprise_id: number;
  plan_date?: string | null;
  time_window_start: string;
  time_window_end: string;
  total_available_power_kw: number;
  status: PlanStatus;
  rule_json?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** 生成请求中的车辆实时状态 */
export interface VehicleState {
  vehicle_id: number;
  current_soc: number;
  target_soc: number;
  max_power_kw: number;
  /** 前端表单用: 是否纳入本次调度 */
  enabled?: boolean;
}

/** 状态展示映射 */
export const PLAN_STATUS_COLORS: Record<PlanStatus, string> = {
  planned: 'blue',
  active: 'processing',
  completed: 'default',
  cancelled: 'red',
};

export const PLAN_STATUS_TEXT: Record<PlanStatus, string> = {
  planned: '待执行',
  active: '执行中',
  completed: '已完成',
  cancelled: '已取消',
};
