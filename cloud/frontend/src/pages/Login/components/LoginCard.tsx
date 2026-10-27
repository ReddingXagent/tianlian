/**
 * 天链 V3 - Login 登录表单卡片（step === 'login'）
 *
 * 密码登录为主入口; 团队开启二次验证(2FA)时, 密码通过后切换为验证码输入。
 * 验证码登录(/auth/sms/login)已停用(后端 410), 不再提供该 Tab。
 */
import React from 'react';
import { USER_TYPE_DESCRIPTIONS } from '../../../utils/auth';
import type { LoginState } from '../hooks/useLogin';
import { styles } from '../constants';

const LoginCard: React.FC<{ login: LoginState }> = ({ login }) => {
  const {
    selectedRole, error, setError,
    username, setUsername, password, setPassword,
    secondFactorRequired, phoneMasked, twoFactorMethod,
    twoFactorCode, setTwoFactorCode,
    loading,
    handlePasswordLogin, handleVerify2FA,
    setShowResetModal, handleBackToSelect,
  } = login;

  if (!selectedRole) return null;

  return (
    <div style={styles.card}>
      {/* Logo区域 */}
      <div style={styles.logoSection}>
        <div style={{
          ...styles.logoIcon,
          background: selectedRole.gradient,
        }}>
          <span style={{ fontSize: 24 }}>{selectedRole.icon}</span>
        </div>
        <h1 style={styles.title}>{selectedRole.welcome}</h1>
        <p style={styles.subtitle}>{selectedRole.title} · {USER_TYPE_DESCRIPTIONS[selectedRole.type]}</p>
      </div>

      {/* 错误提示 */}
      {error && <div style={styles.errorBanner}>{error}</div>}

      {secondFactorRequired ? (
        /* 两步登录(2FA): 输入短信验证码 */
        <form onSubmit={handleVerify2FA} style={styles.form}>
          <div style={styles.inputGroup}>
            <label style={styles.label}>短信验证码</label>
            <p style={{ ...styles.subtitle, margin: '0 0 8px' }}>
              已向手机 {phoneMasked || '绑定手机'} 发送{twoFactorMethod === 'sms' ? '短信' : ''}验证码，请输入收到的6位验证码
            </p>
            <input
              type="text"
              placeholder="请输入6位验证码"
              value={twoFactorCode}
              onChange={e => setTwoFactorCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              style={styles.input}
              maxLength={6}
              autoFocus
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            style={{
              ...styles.submitBtn,
              background: selectedRole.gradient,
              ...(loading ? styles.btnDisabled : {}),
            }}
          >
            {loading ? '验证中...' : '验证并登录'}
          </button>
        </form>
      ) : (
        /* 密码登录表单 */
        <form onSubmit={handlePasswordLogin} style={styles.form}>
          <div style={styles.inputGroup}>
            <label style={styles.label}>用户名</label>
            <input
              type="text"
              placeholder="请输入用户名"
              value={username}
              onChange={e => setUsername(e.target.value)}
              style={styles.input}
              autoFocus
            />
          </div>
          <div style={styles.inputGroup}>
            <label style={styles.label}>密码</label>
            <input
              type="password"
              placeholder="请输入密码"
              value={password}
              onChange={e => setPassword(e.target.value)}
              style={styles.input}
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            style={{
              ...styles.submitBtn,
              background: selectedRole.gradient,
              ...(loading ? styles.btnDisabled : {}),
            }}
          >
            {loading ? '登录中...' : '登 录'}
          </button>

          <div style={styles.linkRow}>
            <span />
            <button
              type="button"
              style={styles.linkBtn}
              onClick={() => { setShowResetModal(true); setError(''); }}
            >
              忘记密码？
            </button>
          </div>
        </form>
      )}

      {/* 返回选择 */}
      <div style={styles.backRow}>
        <button
          type="button"
          style={{
            ...styles.linkBtn,
            color: selectedRole.color,
          }}
          onClick={handleBackToSelect}
        >
          ← 选择其他登录入口
        </button>
      </div>

      {/* 页脚 */}
      <div style={styles.footer}>
        <span>天链光储充运维系统 V3</span>
        <span style={styles.footerDot}>·</span>
        <span>{selectedRole.title}</span>
      </div>
    </div>
  );
};

export default LoginCard;
