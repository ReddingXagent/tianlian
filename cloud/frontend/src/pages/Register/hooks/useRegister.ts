/**
 * 天链 V3 - Register 企业注册数据 hook (任务卡 78c7404b)
 *
 * 表单状态 + 字段校验 + 执照上传 + 提交企业注册申请。
 * 成功后切到 success 视图(资料已提交等待审核)。
 */
import { useState, useCallback, type FormEvent } from 'react';
import { authAPI } from '../../../api';

// 与后端 _CREDIT_CODE_RE / _PHONE_RE 对齐
const CREDIT_CODE_RE = /^[0-9A-HJ-NPQRTUWXY]{18}$/;
const PHONE_RE = /^1[3-9]\d{9}$/;

export type RegisterView = 'form' | 'success';
export type ApplyScope = 'ops' | 'maintenance' | 'both';

export interface RegisterForm {
  company_name: string;
  credit_code: string;
  legal_person: string;
  contact_name: string;
  contact_phone: string;
  contact_email: string;
  password: string;
  confirmPassword: string;
  // 开通范围
  enableOps: boolean;
  enableMaintenance: boolean;
  agreed_to_terms: boolean;
  // 执照
  licenseFile: File | null;
  licenseFilePath: string;
}

const EMPTY_FORM: RegisterForm = {
  company_name: '',
  credit_code: '',
  legal_person: '',
  contact_name: '',
  contact_phone: '',
  contact_email: '',
  password: '',
  confirmPassword: '',
  enableOps: true,
  enableMaintenance: true,
  agreed_to_terms: false,
  licenseFile: null,
  licenseFilePath: '',
};

export function useRegister() {
  const [form, setForm] = useState<RegisterForm>(EMPTY_FORM);
  const [errors, setErrors] = useState<Partial<Record<keyof RegisterForm, string>>>({});
  const [submitError, setSubmitError] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [view, setView] = useState<RegisterView>('form');
  const [submittedCompany, setSubmittedCompany] = useState('');

  const setField = <K extends keyof RegisterForm>(key: K, value: RegisterForm[K]) => {
    setForm(prev => ({ ...prev, [key]: value }));
    setErrors(prev => ({ ...prev, [key]: undefined }));
  };

  // 字段级校验, 返回 errors 映射 (空 = 全通过)
  const validate = useCallback((f: RegisterForm): Partial<Record<keyof RegisterForm, string>> => {
    const e: Partial<Record<keyof RegisterForm, string>> = {};
    if (!f.company_name.trim()) e.company_name = '请输入企业名称';
    if (!CREDIT_CODE_RE.test(f.credit_code)) e.credit_code = '统一社会信用代码需18位合法字符';
    if (!f.contact_name.trim()) e.contact_name = '请输入联系人姓名';
    if (!PHONE_RE.test(f.contact_phone)) e.contact_phone = '手机号格式错误';
    if (f.contact_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.contact_email)) {
      e.contact_email = '邮箱格式错误';
    }
    if (f.password.length < 6) e.password = '密码长度不能少于6位';
    if (f.confirmPassword !== f.password) e.confirmPassword = '两次输入的密码不一致';
    if (!f.enableOps && !f.enableMaintenance) {
      e.enableOps = '请至少选择一个开通平台';
    }
    if (!f.agreed_to_terms) e.agreed_to_terms = '请阅读并同意平台协议';
    return e;
  }, []);

  // 上传执照 → 拿 file_path
  const uploadLicense = useCallback(async () => {
    if (!form.licenseFile) return true;
    setUploading(true);
    setSubmitError('');
    try {
      const res = await authAPI.uploadLicense(form.licenseFile);
      const path = res.data?.file_path || res.data?.data?.file_path || '';
      if (path) {
        setField('licenseFilePath', path);
        return true;
      }
      setSubmitError('执照上传失败，请重试');
      return false;
    } catch (err: any) {
      setSubmitError(err?.response?.data?.detail || '执照上传失败，请重试');
      return false;
    } finally {
      setUploading(false);
    }
  }, [form.licenseFile]);

  // 计算开通范围
  const computeScope = (f: RegisterForm): ApplyScope => {
    if (f.enableOps && f.enableMaintenance) return 'both';
    if (f.enableOps) return 'ops';
    return 'maintenance';
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const fieldErrors = validate(form);
    setErrors(fieldErrors);
    if (Object.keys(fieldErrors).length > 0) return;

    setLoading(true);
    setSubmitError('');
    try {
      // 先上传执照(若有), 再提交
      if (form.licenseFile && !form.licenseFilePath) {
        const ok = await uploadLicense();
        if (!ok) {
          setLoading(false);
          return;
        }
      }
      // 取最新 licenseFilePath (uploadLicense 异步 set, 从 form 读可能尚未更新, 兜底)
      const payload: Record<string, unknown> = {
        company_name: form.company_name.trim(),
        credit_code: form.credit_code.trim().toUpperCase(),
        legal_person: form.legal_person.trim() || undefined,
        contact_name: form.contact_name.trim(),
        contact_phone: form.contact_phone.trim(),
        contact_email: form.contact_email.trim() || undefined,
        password: form.password,
        apply_scope: computeScope(form),
        agreed_to_terms: true,
      };
      if (form.licenseFilePath) payload.license_file_path = form.licenseFilePath;

      await authAPI.registerEnterprise(payload);
      setSubmittedCompany(form.company_name.trim());
      setView('success');
    } catch (err: any) {
      setSubmitError(
        err?.response?.data?.detail || err?.response?.data?.message || '注册提交失败，请稍后重试'
      );
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setForm(EMPTY_FORM);
    setErrors({});
    setSubmitError('');
    setView('form');
    setSubmittedCompany('');
  };

  return {
    form, errors, submitError, loading, uploading, view, submittedCompany,
    setField, validate, uploadLicense, handleSubmit, reset,
  };
}

export type RegisterState = ReturnType<typeof useRegister>;
