/**
 * 天链 V3 - Login 密码重置弹窗
 */
import React from 'react';
import type { LoginState } from '../hooks/useLogin';
import { styles } from '../constants';

const PasswordResetModal: React.FC<{ login: LoginState }> = ({ login }) => {
  const {
    selectedRole,
    resetStep, resetError, resetPhone, setResetPhone,
    resetCode, setResetCode, resetPassword, setResetPassword,
    resetConfirmPassword, setResetConfirmPassword,
    resetLoading, resetCountdown,
    handleSendResetCode, handleResetPassword, closeResetModal,
  } = login;

  return (
    <div style={styles.modalOverlay} onClick={closeResetModal}>
      <div style={styles.modal} onClick={e => e.stopPropagation()}>
        <div style={styles.modalHeader}>
          <h3 style={styles.modalTitle}>重置密码</h3>
          <button style={styles.modalClose} onClick={closeResetModal}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {resetError && <div style={styles.modalError}>{resetError}</div>}

        {resetStep === 'send' && (
          <div style={styles.modalBody}>
            <p style={styles.modalDesc}>请输入账号或手机号，提交密码重置申请</p>
            <div style={styles.inputGroup}>
              <label style={styles.label}>账号 / 手机号</label>
              <input
                type="text"
                placeholder="请输入账号或手机号"
                value={resetPhone}
                onChange={e => setResetPhone(e.target.value)}
                style={styles.input}
                maxLength={50}
                autoFocus
              />
            </div>
            <button
              type="button"
              disabled={resetLoading || resetPhone.trim().length < 2}
              style={{
                ...styles.submitBtn,
                background: selectedRole?.gradient,
                ...(resetLoading || resetPhone.trim().length < 2 ? styles.btnDisabled : {}),
              }}
              onClick={handleSendResetCode}
            >
              {resetLoading ? '提交中...' : '提交重置申请'}
            </button>
          </div>
        )}

        {resetStep === 'done' && (
          <div style={styles.modalBody}>
            <p style={{ ...styles.modalDesc, textAlign: 'center', margin: '12px 0' }}>
              ✅ 申请已提交
            </p>
            <p style={styles.modalDesc}>
              请联系平台管理员处理。管理员核实后会为您重置密码并提供临时密码，
              登录后请尽快修改。
            </p>
            <button
              type="button"
              style={{
                ...styles.submitBtn,
                background: selectedRole?.gradient,
              }}
              onClick={closeResetModal}
            >
              我知道了
            </button>
          </div>
        )}

        {resetStep === 'reset' && (
          <form onSubmit={handleResetPassword} style={styles.modalBody}>
            <p style={styles.modalDesc}>
              验证码已发送至 {resetPhone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2')}
            </p>
            <div style={styles.inputGroup}>
              <label style={styles.label}>验证码</label>
              <div style={styles.codeRow}>
                <input
                  type="text"
                  placeholder="请输入验证码"
                  value={resetCode}
                  onChange={e => setResetCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  style={{ ...styles.input, flex: 1 }}
                  maxLength={6}
                />
                <button
                  type="button"
                  disabled={resetCountdown > 0}
                  style={{
                    ...styles.codeBtn,
                    ...(resetCountdown > 0 ? styles.codeBtnDisabled : {}),
                  }}
                  onClick={handleSendResetCode}
                >
                  {resetCountdown > 0 ? `${resetCountdown}s` : '重新发送'}
                </button>
              </div>
            </div>
            <div style={styles.inputGroup}>
              <label style={styles.label}>新密码</label>
              <input
                type="password"
                placeholder="至少6位密码"
                value={resetPassword}
                onChange={e => setResetPassword(e.target.value)}
                style={styles.input}
              />
            </div>
            <div style={styles.inputGroup}>
              <label style={styles.label}>确认密码</label>
              <input
                type="password"
                placeholder="再次输入新密码"
                value={resetConfirmPassword}
                onChange={e => setResetConfirmPassword(e.target.value)}
                style={styles.input}
              />
            </div>
            <button
              type="submit"
              disabled={resetLoading || !resetCode || !resetPassword}
              style={{
                ...styles.submitBtn,
                background: selectedRole?.gradient,
                ...(resetLoading || !resetCode || !resetPassword ? styles.btnDisabled : {}),
              }}
            >
              {resetLoading ? '重置中...' : '确认重置'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};

export default PasswordResetModal;
