/**
 * 天链 V3 - Login 角色选择视图（step === 'select'）
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import type { RoleCardConfig } from '../types';
import { ROLE_CARDS, styles } from '../constants';

interface Props {
  onSelect: (role: RoleCardConfig) => void;
}

const RoleSelectView: React.FC<Props> = ({ onSelect }) => {
  const navigate = useNavigate();
  return (
    <div style={styles.selectContainer}>
      {/* 顶部标题 */}
      <div style={styles.selectHeader}>
        <div style={styles.selectLogo}>
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
        </div>
        <h1 style={styles.selectTitle}>天链光储充运维系统</h1>
        <p style={styles.selectSubtitle}>请选择您的登录入口</p>
      </div>

      {/* 4张角色卡片 */}
      <div style={styles.cardGrid}>
        {ROLE_CARDS.map(role => (
          <div
            key={role.type}
            style={{
              ...styles.roleCard,
              borderColor: role.colorLight,
            }}
            onClick={() => onSelect(role)}
            onMouseEnter={e => {
              e.currentTarget.style.transform = 'translateY(-4px)';
              e.currentTarget.style.boxShadow = `0 12px 32px ${role.colorLight}`;
              e.currentTarget.style.borderColor = role.color;
            }}
            onMouseLeave={e => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(30,25,24,0.12)';
              e.currentTarget.style.borderColor = role.colorLight;
            }}
          >
            {/* 图标 */}
            <div style={{
              ...styles.roleIcon,
              background: role.gradient,
            }}>
              <span style={styles.roleEmoji}>{role.icon}</span>
            </div>
            {/* 文字 */}
            <h3 style={{
              ...styles.roleTitle,
              color: role.color,
            }}>{role.title}</h3>
            <p style={styles.roleSubtitle}>{role.subtitle}</p>
            {/* 进入按钮 */}
            <div style={{
              ...styles.roleEnterBtn,
              background: role.colorLight,
              color: role.color,
              borderColor: role.color,
            }}>
              进入
            </div>
          </div>
        ))}
      </div>

      {/* 企业注册入口 */}
      <div style={{ marginTop: '24px', fontSize: '14px' }}>
        <span style={{ color: '#777270' }}>还没有企业账户？</span>
        <button
          type="button"
          onClick={() => navigate('/register')}
          style={{
            border: 'none',
            background: 'transparent',
            color: '#ff5a36',
            fontSize: '14px',
            cursor: 'pointer',
            fontWeight: '600',
            marginLeft: '4px',
          }}
        >
          企业注册 →
        </button>
      </div>

      {/* 页脚 */}
      <div style={styles.footer}>
        <span>天链光储充运维系统 V3</span>
        <span style={styles.footerDot}>·</span>
        <span>技术支持</span>
      </div>
    </div>
  );
};

export default RoleSelectView;
