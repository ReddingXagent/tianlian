/**
 * 工单管理页面 — 类型定义
 */
export interface WorkOrder {
  id: string;
  fault_desc: string;
  type: string;
  level: string;
  status: string;
  station_id: number | null;
  device_id: number | null;
  assignee_id: number | null;
  creator_id: number;
  create_time: string;
  accept_time: string | null;
  finish_time: string | null;
  solution: string | null;
}
