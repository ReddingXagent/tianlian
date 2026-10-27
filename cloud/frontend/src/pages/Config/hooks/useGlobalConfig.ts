/**
 * 天链 V3 - 系统配置：全局配置数据 hook
 */
import { useState, useEffect } from 'react';
import { Form, message } from 'antd';
import { globalConfigAPI } from '../../../api';

export function useGlobalConfig() {
  const [globalConfig, setGlobalConfig] = useState({
    system_name: '', logo_url: '', copyright: '', login_bg_url: '', language: 'zh-CN',
  });
  const [globalLoading, setGlobalLoading] = useState(false);
  const [globalForm] = Form.useForm();

  const fetchGlobalConfig = async () => {
    setGlobalLoading(true);
    try {
      const res: any = await globalConfigAPI.get();
      const data = res?.data || res;
      setGlobalConfig(data);
      globalForm.setFieldsValue(data);
    } catch { message.error('获取全局配置失败'); }
    finally { setGlobalLoading(false); }
  };

  const handleGlobalSave = async () => {
    try {
      const values = await globalForm.validateFields();
      const res: any = await globalConfigAPI.update(values);
      const data = res?.data || res;
      setGlobalConfig(data);
      message.success('全局配置已保存');
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '保存失败');
    }
  };

  useEffect(() => {
    fetchGlobalConfig();
  }, []);

  return {
    globalConfig, globalLoading, globalForm,
    fetchGlobalConfig, handleGlobalSave,
  };
}
