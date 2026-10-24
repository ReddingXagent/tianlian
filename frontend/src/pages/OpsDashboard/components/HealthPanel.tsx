/**
 * 右栏：健康度评分（整体健康度仪表盘 + 分布 + 站点排行 + 24h自愈统计）
 */
import React from 'react';
import { Progress, Badge } from 'antd';
import { HeartOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { COLORS } from '../constants';
import type { HealthData, OverviewStats } from '../types';

const getScoreColor = (score: number) => {
  if (score >= 90) return COLORS.success;
  if (score >= 80) return COLORS.info;
  if (score >= 60) return COLORS.warning;
  return COLORS.danger;
};

const HealthPanel: React.FC<{
  health: HealthData | null;
  overview: OverviewStats | null;
}> = ({ health, overview }) => {
  const navigate = useNavigate();
  return (
  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12 }}>
    {/* 整体健康度 */}
    <div style={{
      background: COLORS.bgCard,
      border: `1px solid ${COLORS.border}`,
      borderRadius: 8,
      padding: 16,
      textAlign: 'center',
    }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: COLORS.accent, marginBottom: 12 }}>
        <HeartOutlined style={{ marginRight: 6 }} />系统健康度
      </div>
      <div style={{ position: 'relative', width: 140, height: 140, margin: '0 auto' }}>
        <Progress
          type="dashboard"
          percent={health?.overall_score || 0}
          strokeColor={getScoreColor(health?.overall_score || 0)}
          trailColor="rgba(255,255,255,0.1)"
          strokeWidth={8}
          format={percent => (
            <div>
              <div style={{ fontSize: 32, fontWeight: 700, color: getScoreColor(percent || 0) }}>{percent}</div>
              <div style={{ fontSize: 11, color: COLORS.textDim }}>分</div>
            </div>
          )}
        />
      </div>
      <div style={{ display: 'flex', justifyContent: 'center', gap: 16, marginTop: 8 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 600, color: COLORS.success }}>{health?.total_online || 0}</div>
          <div style={{ fontSize: 10, color: COLORS.textDim }}>在线设备</div>
        </div>
        <div>
          <div style={{ fontSize: 18, fontWeight: 600, color: COLORS.danger }}>{health?.total_fault || 0}</div>
          <div style={{ fontSize: 10, color: COLORS.textDim }}>故障设备</div>
        </div>
        <div>
          <div style={{ fontSize: 18, fontWeight: 600, color: COLORS.info }}>{health?.overall_online_rate?.toFixed(1) || 0}%</div>
          <div style={{ fontSize: 10, color: COLORS.textDim }}>在线率</div>
        </div>
      </div>
    </div>

    {/* 健康度分布 */}
    <div style={{
      background: COLORS.bgCard,
      border: `1px solid ${COLORS.border}`,
      borderRadius: 8,
      padding: 16,
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.accent, marginBottom: 12 }}>
        站点健康度分布
      </div>
      {health?.distribution && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          {[
            { label: '优秀', count: health.distribution.excellent, color: COLORS.success },
            { label: '良好', count: health.distribution.good, color: COLORS.info },
            { label: '警告', count: health.distribution.warning, color: COLORS.warning },
            { label: '故障', count: health.distribution.fault, color: COLORS.danger },
          ].map(item => (
            <div key={item.label} style={{
              flex: 1,
              textAlign: 'center',
              padding: '6px 0',
              borderRadius: 4,
              background: `${item.color}22`,
              border: `1px solid ${item.color}44`,
            }}>
              <div style={{ fontSize: 18, fontWeight: 700, color: item.color }}>{item.count}</div>
              <div style={{ fontSize: 10, color: COLORS.textDim }}>{item.label}</div>
            </div>
          ))}
        </div>
      )}
    </div>

    {/* 各站点健康度列表 */}
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
        fontSize: 13,
        fontWeight: 600,
        color: COLORS.accent,
      }}>
        站点健康度排行
        <span style={{ float: 'right', fontSize: 10, fontWeight: 400, color: COLORS.textDim }}>点击站点→诊断</span>
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
        {(health?.stations || [])
          .sort((a, b) => a.health_score - b.health_score) // 低分在前
          .map(station => (
            <div key={station.station_id} title="点击进入故障诊断"
              onClick={() => navigate('/fault-diagnosis')} style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 8px',
              marginBottom: 4,
              borderRadius: 4,
              background: `${getScoreColor(station.health_score)}11`,
              cursor: 'pointer',
            }}>
              <Badge color={getScoreColor(station.health_score)} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {station.station_name}
                </div>
                <div style={{ fontSize: 10, color: COLORS.textDim }}>
                  {station.online_count}/{station.device_count} 在线
                </div>
              </div>
              <div style={{ width: 60, textAlign: 'right' }}>
                <Progress
                  percent={station.health_score}
                  size="small"
                  strokeColor={getScoreColor(station.health_score)}
                  trailColor="rgba(255,255,255,0.1)"
                  format={p => <span style={{ fontSize: 11, color: getScoreColor(p || 0) }}>{p}</span>}
                />
              </div>
            </div>
          ))}
      </div>
    </div>

    {/* 自愈统计 */}
    <div style={{
      background: COLORS.bgCard,
      border: `1px solid ${COLORS.border}`,
      borderRadius: 8,
      padding: 12,
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.accent, marginBottom: 8 }}>
        <SafetyCertificateOutlined style={{ marginRight: 6 }} />24h自愈统计
      </div>
      <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.success }}>{overview?.healing.success_24h || 0}</div>
          <div style={{ fontSize: 10, color: COLORS.textDim }}>成功</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.info }}>{overview?.healing.total_24h || 0}</div>
          <div style={{ fontSize: 10, color: COLORS.textDim }}>总次数</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.accent }}>{overview?.healing.success_rate?.toFixed(0) || 0}%</div>
          <div style={{ fontSize: 10, color: COLORS.textDim }}>成功率</div>
        </div>
      </div>
    </div>
  </div>
  );
}

export default HealthPanel;
