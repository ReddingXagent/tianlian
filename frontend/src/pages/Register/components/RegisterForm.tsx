/**
 * 天链 V3 - Register 企业注册表单 (任务卡 78c7404b)
 *
 * 字段: 企业名称/统一信用代码/营业执照(预览)/负责人/联系人手机/邮箱/密码/确认密码
 * 开通范围: 运营管理平台 + 运维管理平台(可复选)
 * 协议: 必读弹窗 + 必勾同意方可提交
 */
import React, { useState } from 'react';
import type { RegisterState } from '../hooks/useRegister';
import { PLATFORM_TERMS, styles } from '../constants';

const RegisterForm: React.FC<{ reg: RegisterState }> = ({ reg }) => {
  const { form, errors, setField, handleSubmit, loading, uploading, submitError } = reg;
  const [showTerms, setShowTerms] = useState(false);
  const [previewUrl, setPreviewUrl] = useState('');

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setField('licenseFile', file);
    setField('licenseFilePath', '');
    if (file && file.type.startsWith('image/')) {
      setPreviewUrl(URL.createObjectURL(file));
    } else {
      setPreviewUrl('');
    }
  };

  const inputStyle = (key: keyof typeof form): React.CSSProperties => ({
    ...styles.input,
    ...(errors[key] ? styles.inputError : {}),
  });

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <div style={styles.logo}>🏢</div>
        <h1 style={styles.title}>企业注册</h1>
        <p style={styles.subtitle}>填写企业资料，提交后等待平台审核</p>
      </div>

      {submitError && <div style={styles.errorBanner}>{submitError}</div>}

      <form onSubmit={handleSubmit} style={styles.form}>
        {/* 企业名称 */}
        <div style={styles.inputGroup}>
          <label style={styles.label}>企业名称 *</label>
          <input
            style={inputStyle('company_name')}
            value={form.company_name}
            onChange={e => setField('company_name', e.target.value)}
            placeholder="请输入企业全称"
          />
          {errors.company_name && <p style={styles.errorText}>{errors.company_name}</p>}
        </div>

        {/* 统一信用代码 */}
        <div style={styles.inputGroup}>
          <label style={styles.label}>统一社会信用代码 *</label>
          <input
            style={inputStyle('credit_code')}
            value={form.credit_code}
            onChange={e => setField('credit_code', e.target.value.toUpperCase())}
            placeholder="18位统一社会信用代码"
            maxLength={18}
          />
          {errors.credit_code && <p style={styles.errorText}>{errors.credit_code}</p>}
        </div>

        {/* 营业执照 */}
        <div style={styles.inputGroup}>
          <label style={styles.label}>营业执照</label>
          <label style={styles.fileLabel}>
            {form.licenseFile ? form.licenseFile.name : '点击上传营业执照（图片/PDF，≤10MB）'}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp,application/pdf"
              onChange={onFileChange}
              style={{ display: 'none' }}
            />
          </label>
          {previewUrl && <img src={previewUrl} alt="执照预览" style={styles.previewImg} />}
          {uploading && <p style={styles.hint}>上传中...</p>}
        </div>

        {/* 负责人 + 联系人 */}
        <div style={styles.row}>
          <div style={styles.inputGroup}>
            <label style={styles.label}>负责人 / 法人</label>
            <input
              style={inputStyle('legal_person')}
              value={form.legal_person}
              onChange={e => setField('legal_person', e.target.value)}
              placeholder="法定代表人或负责人"
            />
          </div>
          <div style={styles.inputGroup}>
            <label style={styles.label}>联系人 *</label>
            <input
              style={inputStyle('contact_name')}
              value={form.contact_name}
              onChange={e => setField('contact_name', e.target.value)}
              placeholder="联系人姓名"
            />
            {errors.contact_name && <p style={styles.errorText}>{errors.contact_name}</p>}
          </div>
        </div>

        {/* 手机 + 邮箱 */}
        <div style={styles.row}>
          <div style={styles.inputGroup}>
            <label style={styles.label}>联系人手机 *</label>
            <input
              style={inputStyle('contact_phone')}
              value={form.contact_phone}
              onChange={e => setField('contact_phone', e.target.value.replace(/\D/g, '').slice(0, 11))}
              placeholder="11位手机号"
              maxLength={11}
            />
            {errors.contact_phone && <p style={styles.errorText}>{errors.contact_phone}</p>}
          </div>
          <div style={styles.inputGroup}>
            <label style={styles.label}>邮箱</label>
            <input
              style={inputStyle('contact_email')}
              value={form.contact_email}
              onChange={e => setField('contact_email', e.target.value)}
              placeholder="联系邮箱(可选)"
            />
            {errors.contact_email && <p style={styles.errorText}>{errors.contact_email}</p>}
          </div>
        </div>

        {/* 密码 */}
        <div style={styles.row}>
          <div style={styles.inputGroup}>
            <label style={styles.label}>登录密码 *</label>
            <input
              type="password"
              style={inputStyle('password')}
              value={form.password}
              onChange={e => setField('password', e.target.value)}
              placeholder="≥6位"
            />
            {errors.password && <p style={styles.errorText}>{errors.password}</p>}
          </div>
          <div style={styles.inputGroup}>
            <label style={styles.label}>确认密码 *</label>
            <input
              type="password"
              style={inputStyle('confirmPassword')}
              value={form.confirmPassword}
              onChange={e => setField('confirmPassword', e.target.value)}
              placeholder="再次输入密码"
            />
            {errors.confirmPassword && <p style={styles.errorText}>{errors.confirmPassword}</p>}
          </div>
        </div>

        {/* 开通范围 */}
        <div style={styles.inputGroup}>
          <label style={styles.label}>开通范围 *</label>
          <div style={styles.checkboxRow}>
            <input
              type="checkbox"
              style={styles.checkbox}
              checked={form.enableOps}
              onChange={e => setField('enableOps', e.target.checked)}
            />
            <span>运营管理平台</span>
          </div>
          <div style={styles.checkboxRow}>
            <input
              type="checkbox"
              style={styles.checkbox}
              checked={form.enableMaintenance}
              onChange={e => setField('enableMaintenance', e.target.checked)}
            />
            <span>开通运维管理平台</span>
          </div>
          {errors.enableOps && <p style={styles.errorText}>{errors.enableOps}</p>}
        </div>

        {/* 协议 */}
        <div style={styles.checkboxRow}>
          <input
            type="checkbox"
            id="agreeTerms"
            style={styles.checkbox}
            checked={form.agreed_to_terms}
            onChange={e => setField('agreed_to_terms', e.target.checked)}
          />
          <label htmlFor="agreeTerms">
            我已阅读并同意
            <span style={styles.termsLink} onClick={() => setShowTerms(true)}>《天链光储充运营平台服务协议》</span>
          </label>
        </div>
        {errors.agreed_to_terms && <p style={{ ...styles.errorText, marginBottom: '8px' }}>{errors.agreed_to_terms}</p>}

        <button
          type="submit"
          disabled={loading || uploading}
          style={{
            ...styles.submitBtn,
            ...((loading || uploading) ? styles.btnDisabled : {}),
          }}
        >
          {loading ? '提交中...' : '提交注册申请'}
        </button>
      </form>

      <div style={styles.backLink}>
        已有账户?
        <a href="/login" style={styles.linkBtn}>返回登录</a>
      </div>

      {/* 协议弹窗 */}
      {showTerms && (
        <div
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(30,25,24,0.4)', display: 'flex',
            alignItems: 'center', justifyContent: 'center', zIndex: 1000,
          }}
          onClick={() => setShowTerms(false)}
        >
          <div
            style={{
              width: '560px', maxWidth: '90vw', maxHeight: '80vh', overflow: 'auto',
              background: '#fff', borderRadius: '16px', padding: '24px 28px',
            }}
            onClick={e => e.stopPropagation()}
          >
            <h2 style={{ fontSize: '18px', fontWeight: 700, margin: '0 0 16px' }}>
              天链光储充运营平台服务协议
            </h2>
            {PLATFORM_TERMS.map((t, i) => (
              <div key={i} style={{ marginBottom: '14px' }}>
                <h3 style={{ fontSize: '14px', fontWeight: 600, margin: '0 0 4px', color: '#1e1918' }}>
                  {t.title}
                </h3>
                <p style={{ fontSize: '13px', color: '#555', lineHeight: 1.6, margin: 0 }}>{t.body}</p>
              </div>
            ))}
            <button
              onClick={() => setShowTerms(false)}
              style={{
                ...styles.submitBtn, marginTop: '8px', background: 'linear-gradient(135deg, #ff5a36, #ff7a5c)',
              }}
            >
              我已阅读
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default RegisterForm;
