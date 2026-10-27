/**
 * 天链 V3 - 系统配置：发票配置数据 hook
 */
import { useState, useEffect } from 'react';
import { Form, message } from 'antd';
import { invoiceConfigAPI } from '../../../api';

export function useInvoiceConfig() {
  const [invoiceConfig, setInvoiceConfig] = useState<any>({});
  const [invoiceLoading, setInvoiceLoading] = useState(false);
  const [invoiceForm] = Form.useForm();

  const fetchInvoiceConfig = async () => {
    setInvoiceLoading(true);
    try {
      const res: any = await invoiceConfigAPI.get();
      const data = res?.data || res;
      setInvoiceConfig(data);
      invoiceForm.setFieldsValue(data);
    } catch { message.error('获取发票配置失败'); }
    finally { setInvoiceLoading(false); }
  };

  const handleInvoiceSave = async () => {
    try {
      const values = await invoiceForm.validateFields();
      const res: any = await invoiceConfigAPI.update(values);
      const data = res?.data || res;
      setInvoiceConfig(data);
      message.success('发票配置已保存');
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '保存失败');
    }
  };

  useEffect(() => {
    fetchInvoiceConfig();
  }, []);

  return {
    invoiceConfig, invoiceLoading, invoiceForm,
    fetchInvoiceConfig, handleInvoiceSave,
  };
}
