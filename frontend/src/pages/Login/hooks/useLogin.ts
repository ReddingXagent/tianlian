/**
 * 天链 V3 - Login 数据 hook
 *
 * 封装登录流程全部状态与交互：
 *   - 角色选择步骤切换
 *   - 密码登录（主入口）
 *   - 两步登录(2FA, 任务卡 78c7404b): 团队开启二次验证时, 密码通过后输入短信验证码
 *   - 密码重置弹窗（发送验证码 → 重置）
 *
 * 验证码登录(/auth/sms/login)已停用(后端返回 410), 本 hook 不再提供该路径。
 */
import { useState, useEffect, useCallback, type FormEvent } from 'react';
import { setAuth } from '../../../utils/authStorage';
import { useNavigate } from 'react-router-dom';
import { authAPI, forgotPasswordAPI } from '../../../api';
import { setUserType, getDefaultRoute } from '../../../utils/auth';
import type { RoleCardConfig } from '../types';

export function useLogin() {
  const navigate = useNavigate();

  // 步骤：select = 选择角色卡片，login = 登录表单
  const [step, setStep] = useState<'select' | 'login'>('select');
  const [selectedRole, setSelectedRole] = useState<RoleCardConfig | null>(null);

  // 表单字段
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  // 两步登录(2FA)状态: 密码通过后后端返回 second_factor_required + temp_token
  const [secondFactorRequired, setSecondFactorRequired] = useState(false);
  const [tempToken, setTempToken] = useState('');
  const [twoFactorMethod, setTwoFactorMethod] = useState('sms');
  const [phoneMasked, setPhoneMasked] = useState('');
  const [twoFactorCode, setTwoFactorCode] = useState('');

  // 状态
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // 密码重置弹窗
  const [showResetModal, setShowResetModal] = useState(false);
  const [resetPhone, setResetPhone] = useState('');
  const [resetCode, setResetCode] = useState('');
  const [resetPassword, setResetPassword] = useState('');
  const [resetConfirmPassword, setResetConfirmPassword] = useState('');
  const [resetStep, setResetStep] = useState<'send' | 'reset' | 'done'>('send');
  const [resetLoading, setResetLoading] = useState(false);
  const [resetError, setResetError] = useState('');
  const [resetCountdown, setResetCountdown] = useState(0);

  // 倒计时
  useEffect(() => {
    if (resetCountdown > 0) {
      const timer = setInterval(() => setResetCountdown(c => c - 1), 1000);
      return () => clearInterval(timer);
    }
  }, [resetCountdown]);

  // 选择角色 → 进入登录
  const handleSelectRole = (role: RoleCardConfig) => {
    setSelectedRole(role);
    setStep('login');
    setError('');
    setUsername('');
    setPassword('');
    setSecondFactorRequired(false);
    setTempToken('');
    setTwoFactorCode('');
    setPhoneMasked('');
  };

  // 返回角色选择
  const handleBackToSelect = () => {
    setStep('select');
    setSelectedRole(null);
    setError('');
    setSecondFactorRequired(false);
    setTempToken('');
    setTwoFactorCode('');
  };

  // 统一错误处理
  const handleError = useCallback((err: any) => {
    const msg =
      err?.response?.data?.detail ||
      err?.response?.data?.message ||
      err?.message ||
      '操作失败，请稍后重试';
    setError(msg);
    setTimeout(() => setError(''), 5000);
  }, []);

  // 登录成功统一收尾: 存凭证 → 跳默认页
  const finishLogin = (data: any) => {
    const token = data?.token || data?.access_token || '';
    const user = data?.user || data;
    if (!token) {
      setError('登录失败：未获取到令牌');
      return false;
    }
    // portal 隔离(2026-10-09 丁哥: 同浏览器并存运营+运维): 运营人员入口写独立key
    const portal = selectedRole?.type === 'operator' ? 'operate' : 'main';
    setAuth(token, { ...user, user_type: selectedRole?.type }, portal);
    if (selectedRole) setUserType(selectedRole.type);
    navigate(portal === 'operate' ? '/operate' : getDefaultRoute(), { replace: true });
    return true;
  };

  // ========== 密码登录 ==========
  const handlePasswordLogin = async (e: FormEvent) => {
    e.preventDefault();
    if (!username || !password) {
      setError('请输入用户名和密码');
      return;
    }
    if (!selectedRole) return;
    setLoading(true);
    setError('');
    try {
      const res = await authAPI.login(username, password, selectedRole.type);
      const data = res.data;
      // 两步登录(2FA): 后端返回 second_factor_required + temp_token, 不发正式 token
      if (data?.second_factor_required) {
        setSecondFactorRequired(true);
        setTempToken(data.temp_token || '');
        setTwoFactorMethod(data.method || 'sms');
        setPhoneMasked(data.phone_masked || '');
        setTwoFactorCode('');
        setError('');
        return;
      }
      finishLogin(data);
    } catch (err: any) {
      handleError(err);
    } finally {
      setLoading(false);
    }
  };

  // ========== 两步登录: 验证短信码换正式 token ==========
  const handleVerify2FA = async (e: FormEvent) => {
    e.preventDefault();
    if (!twoFactorCode) {
      setError('请输入短信验证码');
      return;
    }
    if (!tempToken) {
      setError('二次验证令牌丢失，请重新登录');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res = await authAPI.verify2FA(tempToken, twoFactorCode);
      finishLogin(res.data);
    } catch (err: any) {
      handleError(err);
    } finally {
      setLoading(false);
    }
  };

  // ========== 密码重置（卡 922b2fba: 短信通道已停用410, 改「提交申请→管理员处理」闭环） ==========
  const handleSendResetCode = async () => {
    const account = resetPhone.trim();
    if (!account || account.length < 2 || account.length > 50) {
      setResetError('请输入账号或手机号');
      return;
    }
    setResetLoading(true);
    setResetError('');
    try {
      await forgotPasswordAPI.submit(account);
      setResetStep('done');
    } catch {
      // 统一文案, 不泄露账号存在性
      setResetStep('done');
    } finally {
      setResetLoading(false);
    }
  };

  const handleResetPassword = async (e: FormEvent) => {
    e.preventDefault();
    if (!resetPhone || !resetCode || !resetPassword) {
      setResetError('请填写完整信息');
      return;
    }
    if (resetPassword.length < 6) {
      setResetError('密码长度不能少于6位');
      return;
    }
    if (resetPassword !== resetConfirmPassword) {
      setResetError('两次输入的密码不一致');
      return;
    }
    setResetLoading(true);
    setResetError('');
    try {
      await authAPI.passwordReset(resetPhone, resetCode, resetPassword);
      setShowResetModal(false);
      setResetPhone('');
      setResetCode('');
      setResetPassword('');
      setResetConfirmPassword('');
      setResetStep('send');
      setError('密码重置成功，请使用新密码登录');
      setTimeout(() => setError(''), 5000);
    } catch (err: any) {
      setResetError(
        err?.response?.data?.detail || err?.response?.data?.message || '重置失败'
      );
    } finally {
      setResetLoading(false);
    }
  };

  const closeResetModal = () => {
    setShowResetModal(false);
    setResetStep('send');
    setResetError('');
    setResetPhone('');
    setResetCode('');
    setResetPassword('');
    setResetConfirmPassword('');
  };

  return {
    // 步骤与角色
    step, selectedRole,
    // 登录表单
    username, setUsername,
    password, setPassword,
    loading, error, setError,
    // 两步登录(2FA)
    secondFactorRequired,
    tempToken,
    twoFactorMethod,
    phoneMasked,
    twoFactorCode, setTwoFactorCode,
    // 重置弹窗
    showResetModal, setShowResetModal,
    resetPhone, setResetPhone,
    resetCode, setResetCode,
    resetPassword, setResetPassword,
    resetConfirmPassword, setResetConfirmPassword,
    resetStep, resetLoading, resetError, resetCountdown,
    // 交互
    handleSelectRole, handleBackToSelect,
    handlePasswordLogin, handleVerify2FA,
    handleSendResetCode, handleResetPassword, closeResetModal,
  };
}

export type LoginState = ReturnType<typeof useLogin>;
