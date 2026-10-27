/**
 * 天链 V3 - Register 注册页 常量 (样式 + 平台协议文本)
 *
 * 协议正文静态内嵌(任务卡 78c7404b): 前端构建后无文件系统访问, 无法运行时读取
 * docs/platform_terms_v1.md, 故将其核心条款精简为常量在协议弹窗中展示。
 * 与后端 _CURRENT_AGREEMENT_VERSION="platform_terms_v1" 对齐。
 */
import type { CSSProperties } from 'react';

export const AGREEMENT_VERSION = 'platform_terms_v1';

// 平台协议条款(精简自 docs/platform_terms_v1.md, 用于注册前必读弹窗)
export const PLATFORM_TERMS: { title: string; body: string }[] = [
  {
    title: '第一条 协议范围与接受',
    body: '本协议是用户注册、使用天链光储充运营平台(含运营管理、运维管理及相关服务)的全部约定。用户勾选同意并完成注册，即视为已充分阅读、理解并接受本协议全部条款。平台方有权根据业务需要修订本协议，修订后于平台公示。',
  },
  {
    title: '第二条 注册与账户',
    body: '用户应以真实企业身份注册，提交企业名称、统一社会信用代码、营业执照、负责人信息、联系人及联系方式，并选择开通运营管理平台和/或运维管理平台。用户保证所提交资料真实、准确、完整、有效；因资料虚假、过期或侵权引起的责任由用户承担。注册申请须经平台方审核，平台方有权自主决定是否批准开通。',
  },
  {
    title: '第三条 服务内容与费用',
    body: '平台向用户提供光储充场站的运营、运维数字化管理服务，具体功能以平台实际上线为准。服务费用(如有)以双方另行签署的商务合同或平台公示价目为准。',
  },
  {
    title: '第四条 数据权利',
    body: '用户在平台产生的业务数据享有使用权；平台方享有对数据进行存储、分析、脱敏后用于产品改进、行业统计及商业研究的权利。涉及个人信息的，双方应遵守相关法律法规。',
  },
  {
    title: '第七条 责任限制(核心条款)',
    body: '平台按"现状"及"现有可用"状态提供，不保证服务永不中断、无误。因不可抗力、基础电信、电力、硬件或第三方系统故障导致的服务异常，平台方免责。在适用法律允许的最大范围内，平台方对用户的任何间接、附带、特殊或惩罚性损失不承担责任；累计赔偿总额不超过用户在损失发生前 12 个月内实际支付的服务费用。',
  },
  {
    title: '第八条 服务暂停与终止',
    body: '用户违约、欠费、涉诉或存在重大安全风险的，平台方有权立即暂停或终止服务。用户可提前 30 日书面申请终止服务。',
  },
  {
    title: '第十条 法律适用与争议解决',
    body: '本协议适用中华人民共和国法律。因本协议产生的争议，双方协商不成的，应提交平台方所在地(深圳市)有管辖权的人民法院诉讼解决。',
  },
];

// ======== 内联样式(与 Login 风格统一) ========
export const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, #faf5f4)',
    position: 'relative',
    overflow: 'hidden',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    padding: '24px',
  },
  card: {
    width: '480px',
    maxWidth: '100%',
    padding: '36px 40px',
    background: '#ffffff',
    borderRadius: '16px',
    boxShadow: '0 25px 50px -12px rgba(30,25,24,0.12)',
    border: '1px solid #e6e1e0',
    position: 'relative',
    zIndex: 1,
  },
  header: {
    textAlign: 'center',
    marginBottom: '24px',
  },
  logo: {
    width: '48px',
    height: '48px',
    margin: '0 auto 12px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, #ff5a36, #ff7a5c)',
    borderRadius: '12px',
    color: '#fff',
    fontSize: '22px',
  },
  title: {
    fontSize: '20px',
    fontWeight: '700',
    color: '#1e1918',
    margin: '0 0 4px',
  },
  subtitle: {
    fontSize: '13px',
    color: '#777270',
    margin: 0,
  },
  form: {
    display: 'flex',
    flexDirection: 'column' as const,
  },
  row: {
    display: 'flex',
    gap: '12px',
  },
  inputGroup: {
    marginBottom: '14px',
    flex: 1,
  },
  label: {
    display: 'block',
    marginBottom: '6px',
    fontSize: '13px',
    fontWeight: '500',
    color: '#777270',
  },
  input: {
    width: '100%',
    padding: '9px 12px',
    border: '1px solid #e6e1e0',
    borderRadius: '8px',
    fontSize: '14px',
    background: '#ffffff',
    color: '#1e1918',
    outline: 'none',
    boxSizing: 'border-box' as const,
  },
  inputError: {
    borderColor: '#ef4444',
  },
  hint: {
    fontSize: '12px',
    color: '#a6a1a0',
    margin: '4px 0 0',
  },
  errorText: {
    fontSize: '12px',
    color: '#ef4444',
    margin: '4px 0 0',
  },
  fileLabel: {
    display: 'inline-block',
    padding: '8px 16px',
    border: '1px solid rgba(255,90,54,0.3)',
    borderRadius: '8px',
    background: 'rgba(255,90,54,0.06)',
    color: '#ff5a36',
    fontSize: '13px',
    cursor: 'pointer',
  },
  previewImg: {
    maxWidth: '100%',
    maxHeight: '120px',
    borderRadius: '8px',
    marginTop: '8px',
    border: '1px solid #e6e1e0',
  },
  checkboxRow: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '8px',
    marginBottom: '14px',
    fontSize: '13px',
    color: '#555',
  },
  checkbox: {
    marginTop: '2px',
    cursor: 'pointer',
  },
  termsLink: {
    color: '#ff5a36',
    cursor: 'pointer',
    textDecoration: 'underline',
  },
  submitBtn: {
    width: '100%',
    padding: '12px',
    border: 'none',
    borderRadius: '8px',
    background: 'linear-gradient(135deg, #ff5a36, #ff7a5c)',
    color: '#fff',
    fontSize: '15px',
    fontWeight: '600',
    cursor: 'pointer',
    marginTop: '4px',
  },
  btnDisabled: {
    opacity: 0.6,
    cursor: 'not-allowed',
  },
  backLink: {
    textAlign: 'center' as const,
    marginTop: '16px',
    fontSize: '13px',
    color: '#777270',
  },
  linkBtn: {
    border: 'none',
    background: 'transparent',
    color: '#ff5a36',
    fontSize: '13px',
    cursor: 'pointer',
    fontWeight: '500',
    marginLeft: '4px',
  },
  errorBanner: {
    padding: '10px 14px',
    marginBottom: '16px',
    borderRadius: '8px',
    background: 'rgba(239,68,68,0.08)',
    border: '1px solid rgba(239,68,68,0.15)',
    color: '#ef4444',
    fontSize: '13px',
  },
  // 成功页
  successBox: {
    textAlign: 'center' as const,
    padding: '24px 0',
  },
  successIcon: {
    width: '64px',
    height: '64px',
    margin: '0 auto 16px',
    borderRadius: '50%',
    background: 'rgba(16,185,129,0.12)',
    color: '#10b981',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '32px',
  },
  successTitle: {
    fontSize: '18px',
    fontWeight: '700',
    color: '#1e1918',
    margin: '0 0 8px',
  },
  successDesc: {
    fontSize: '14px',
    color: '#777270',
    margin: '0 0 24px',
    lineHeight: 1.6,
  },
};
