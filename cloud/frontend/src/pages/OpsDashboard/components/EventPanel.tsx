/**
 * 中栏：事件流（事件统计 + 实时事件列表）
 *
 * 2026-10-10 丁哥定调: 大屏参与状态展示, 不参与管理调度 —
 * 统计卡/事件条目可点击跳转对应详情页(告警页/工单页), 无任何写操作;
 * 处理与派单在专门页面完成。
 */
import React, { useState } from 'react';
import { Tag, message } from 'antd';
import {
  AlertOutlined, CheckCircleOutlined, WarningOutlined, SafetyCertificateOutlined,
  MedicineBoxOutlined, ToolOutlined, CheckOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { COLORS } from '../constants';
import { workorderAPI } from '../../../api';
import type { EventItem, OverviewStats } from '../types';

const getEventIcon = (type: string) => {
  switch (type) {
    case 'alarm': return <AlertOutlined style={{ color: COLORS.danger }} />;
    case 'workorder': return <CheckCircleOutlined style={{ color: COLORS.info }} />;
    case 'healing': return <SafetyCertificateOutlined style={{ color: COLORS.success }} />;
    default: return <WarningOutlined />;
  }
};

const getEventColor = (type: string, level: string) => {
  if (type === 'healing') return COLORS.success;
  if (level === 'critical') return COLORS.danger;
  if (level === 'warning') return COLORS.warning;
  return COLORS.info;
};

const formatTime = (ts?: string) => {
  if (!ts) return '';
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
};

const EventPanel: React.FC<{
  overview: OverviewStats | null;
  events: EventItem[];
  listRef: React.RefObject<HTMLDivElement>;
}> = ({ overview, events, listRef }) => {
  const navigate = useNavigate();

  const [dispatchingId, setDispatchingId] = useState<string | null>(null);
  const [dispatched, setDispatched] = useState<Set<string>>(new Set());

  const goEvent = (e: EventItem) => {
    if (e.type === 'alarm') navigate('/alarms');
    else if (e.type === 'workorder') navigate('/workorders');
  };

  const createWorkOrder = async (e: EventItem) => {
    if (dispatched.has(e.id)) return;
    setDispatchingId(e.id);
    try {
      await workorderAPI.create({
        fault_desc: `[大屏派单] ${e.title} | 站点: ${e.station_name || '-'} | 设备: ${e.device_name || '-'} | 告警类型: ${e.alarm_type || '-'} | 级别: ${e.level}`,
        type: 'repair',
        level: e.level === 'critical' ? 'critical' : 'warning',
        source: 'alarm',
      } as never);
      setDispatched((prev) => new Set(prev).add(e.id));
      message.success(`工单已创建，待运维接单: ${e.title.slice(0, 14)}…`);
    } catch (err: unknown) {
      message.error('派单失败: ' + ((err as any)?.response?.data?.detail || (err as any)?.message));
    } finally {
      setDispatchingId(null);
    }
  };

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* 事件统计(点击跳转) */}
      <div style={{ display: 'flex', gap: 8 }}>
        {[
          { label: '活跃告警', value: overview?.alarms.active || 0, color: COLORS.danger, to: '/alarms' },
          { label: '严重告警', value: overview?.alarms.critical || 0, color: '#ff4d4f', to: '/alarms' },
          { label: '待处理工单', value: overview?.workorders.pending || 0, color: COLORS.warning, to: '/workorders' },
          { label: '自愈成功', value: overview?.healing.success_24h || 0, color: COLORS.success, to: null },
        ].map(item => (
          <div key={item.label} style={{
            flex: 1,
            background: COLORS.bgCard,
            border: `1px solid ${COLORS.border}`,
            borderRadius: 8,
            padding: '8px 6px',
            textAlign: 'center',
            cursor: item.to ? 'pointer' : 'default',
          }}
            onClick={() => item.to && navigate(item.to)}>
            <div style={{ fontSize: 20, fontWeight: 700, color: item.color }}>{item.value}</div>
            <div style={{ fontSize: 10, color: COLORS.textDim }}>{item.label}</div>
          </div>
        ))}
      </div>

      {/* 事件列表 */}
      <div style={{
        flex: 1,
        background: COLORS.bgCard,
        border: `1px solid ${COLORS.border}`,
        borderRadius: 8,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        <div style={{
          padding: '10px 16px',
          borderBottom: `1px solid ${COLORS.border}`,
          fontSize: 14,
          fontWeight: 600,
          color: COLORS.accent,
        }}>
          <AlertOutlined style={{ marginRight: 6 }} />事件流
          <Tag color="blue" style={{ marginLeft: 8, fontSize: 10 }}>{events.length}条</Tag>
          <span style={{ float: 'right', fontSize: 10, fontWeight: 400, color: COLORS.textDim }}>
            点击跳转 · 告警可诊断/派单
          </span>
        </div>
        <div ref={listRef} style={{ flex: 1, overflow: 'auto', padding: 8 }}>
          {events.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40, color: COLORS.textDim }}>
              <CheckCircleOutlined style={{ fontSize: 32, marginBottom: 8, display: 'block' }} />
              暂无事件，系统运行正常
            </div>
          ) : (
            events.map(event => (
              <div key={event.id} style={{
                padding: '8px 12px',
                marginBottom: 6,
                borderRadius: 6,
                background: `${getEventColor(event.type, event.level)}11`,
                borderLeft: `3px solid ${getEventColor(event.type, event.level)}`,
                display: 'flex',
                alignItems: 'flex-start',
                gap: 8,
                cursor: event.type !== 'healing' ? 'pointer' : 'default',
              }}
                onClick={() => goEvent(event)}>
                <div style={{ marginTop: 2 }}>{getEventIcon(event.type)}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: COLORS.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {event.title}
                    </span>
                    <Tag color={event.type === 'alarm' ? 'red' : event.type === 'healing' ? 'green' : 'blue'} style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', marginLeft: 4, flexShrink: 0 }}>
                      {event.type === 'alarm' ? '告警' : event.type === 'workorder' ? '工单' : '自愈'}
                    </Tag>
                  </div>
                  <div style={{ fontSize: 10, color: COLORS.textDim }}>
                    {event.station_name && <span>{event.station_name}</span>}
                    {event.device_name && <span> · {event.device_name}</span>}
                    {event.type === 'alarm' && event.alarm_type && <span> · {event.alarm_type}</span>}
                    {event.created_at && <span> · {formatTime(event.created_at)}</span>}
                  </div>
                  {event.type === 'alarm' && (
                    <div style={{ display: 'flex', gap: 6, marginTop: 4 }} onClick={(ev) => ev.stopPropagation()}>
                      <span
                        style={{ fontSize: 10, color: COLORS.accent, cursor: 'pointer', border: `1px solid ${COLORS.accent}55`, borderRadius: 4, padding: '1px 6px' }}
                        onClick={() => navigate('/fault-diagnosis')}>
                        <MedicineBoxOutlined /> 诊断
                      </span>
                      {dispatched.has(event.id) ? (
                        <span style={{ fontSize: 10, color: COLORS.success, border: `1px solid ${COLORS.success}55`, borderRadius: 4, padding: '1px 6px' }}>
                          <CheckOutlined /> 已派单
                        </span>
                      ) : (
                        <span
                          style={{ fontSize: 10, color: COLORS.warning, cursor: 'pointer', border: `1px solid ${COLORS.warning}55`, borderRadius: 4, padding: '1px 6px', opacity: dispatchingId === event.id ? 0.5 : 1 }}
                          onClick={() => createWorkOrder(event)}>
                          <ToolOutlined /> {dispatchingId === event.id ? '派单中…' : '派单'}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default EventPanel;
