/**
 * 天链V3 — 数据大屏告警滚动条
 *
 * Phase48: requestAnimationFrame 驱动的自动滚动告警列表，悬停暂停
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  CARD_BG,
  CARD_BORDER,
  DANGER_COLOR,
  PRIMARY_COLOR,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  WARNING_COLOR,
} from '../constants';
import type { RecentAlarm } from '../types';

const getLevelColor = (level: string) => {
  switch (level) {
    case 'critical':
      return DANGER_COLOR;
    case 'warning':
    case 'major':
      return WARNING_COLOR;
    default:
      return PRIMARY_COLOR;
  }
};

const AlarmTicker: React.FC<{ alarms: RecentAlarm[] }> = ({ alarms }) => {
  const tickerRef = useRef<HTMLDivElement>(null);
  const [animPaused, setAnimPaused] = useState(false);

  useEffect(() => {
    if (!tickerRef.current || alarms.length === 0) return;

    let animationId: number;
    const scroll = () => {
      const el = tickerRef.current;
      if (!el) return;
      // autoScroll
      if (!animPaused) {
        el.scrollTop += 1;
        if (el.scrollTop >= el.scrollHeight - el.clientHeight) {
          el.scrollTop = 0;
        }
      }
      animationId = requestAnimationFrame(scroll);
    };
    animationId = requestAnimationFrame(scroll);
    return () => cancelAnimationFrame(animationId);
  }, [alarms, animPaused]);

  if (alarms.length === 0) {
    return (
      <div
        style={{
          background: CARD_BG,
          border: CARD_BORDER,
          borderRadius: 8,
          padding: 16,
          height: 260,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: TEXT_SECONDARY,
          fontSize: 14,
        }}
      >
        暂无活跃告警 ✓
      </div>
    );
  }

  return (
    <div
      style={{
        background: CARD_BG,
        border: CARD_BORDER,
        borderRadius: 8,
        padding: 16,
        height: 260,
        position: 'relative',
      }}
      onMouseEnter={() => setAnimPaused(true)}
      onMouseLeave={() => setAnimPaused(false)}
    >
      <div
        style={{
          fontSize: 14,
          fontWeight: 600,
          color: TEXT_PRIMARY,
          marginBottom: 12,
          paddingBottom: 8,
          borderBottom: '1px solid rgba(24,144,255,0.2)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span>⚠ 实时告警</span>
        <span style={{ fontSize: 11, color: TEXT_SECONDARY }}>
          {alarms.length} 条
        </span>
      </div>
      <div
        ref={tickerRef}
        style={{
          height: 200,
          overflow: 'hidden',
          scrollBehavior: 'smooth',
        }}
      >
        {alarms.map((a, i) => (
          <div
            key={a.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 0',
              borderBottom: i < alarms.length - 1 ? '1px solid rgba(255,255,255,0.05)' : 'none',
              fontSize: 12,
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: getLevelColor(a.level),
                flexShrink: 0,
                boxShadow: `0 0 6px ${getLevelColor(a.level)}`,
              }}
            />
            <span style={{ color: TEXT_PRIMARY, flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {a.title}
            </span>
            <span style={{ color: TEXT_SECONDARY, fontSize: 11, flexShrink: 0 }}>
              {a.station_name}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AlarmTicker;
