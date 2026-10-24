/**
 * 天链 V3 - Register 企业注册页 (任务卡 78c7404b)
 *
 * 两态: form(填写) → success(资料已提交, 等待平台审核)。
 * 后端无匿名申请状态查询端点(审批端点需平台 admin), 故 success 页提示
 * 审核通过后凭注册手机号+密码登录, 不做查询(mock 无意义)。
 */
import React from 'react';
import { useRegister } from './hooks/useRegister';
import RegisterForm from './components/RegisterForm';
import { styles } from './constants';

export default function RegisterPage() {
  const reg = useRegister();

  return (
    <div style={styles.page}>
      {reg.view === 'success' ? (
        <div style={styles.card}>
          <div style={styles.successBox}>
            <div style={styles.successIcon}>✓</div>
            <h1 style={styles.successTitle}>资料已提交，等待平台审核</h1>
            <p style={styles.successDesc}>
              {reg.submittedCompany ? `「${reg.submittedCompany}」` : '您的企业'}的注册申请已提交成功。
              平台审核通过后，您将收到开通通知，届时可凭注册时填写的手机号对应的账户与密码登录。
            </p>
            <a href="/login" style={{ ...styles.linkBtn, fontSize: '14px' }}>返回登录</a>
          </div>
        </div>
      ) : (
        <RegisterForm reg={reg} />
      )}
    </div>
  );
}
