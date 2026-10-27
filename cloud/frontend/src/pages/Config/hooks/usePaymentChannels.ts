/**
 * 天链 V3 - 系统配置：支付通道数据 hook
 */
import { useState, useEffect } from 'react';
import { Form, message } from 'antd';
import { paymentChannelAPI } from '../../../api';

export function usePaymentChannels() {
  const [payChannels, setPayChannels] = useState<any[]>([]);
  const [payLoading, setPayLoading] = useState(false);
  const [payModalVisible, setPayModalVisible] = useState(false);
  const [editingChannel, setEditingChannel] = useState<any>(null);
  const [payForm] = Form.useForm();

  const fetchPayChannels = async () => {
    setPayLoading(true);
    try {
      const res: any = await paymentChannelAPI.list();
      const data = res?.data || res;
      setPayChannels(data.items || []);
    } catch { message.error('获取支付通道失败'); }
    finally { setPayLoading(false); }
  };

  const openCreateChannel = () => {
    setEditingChannel(null);
    payForm.resetFields();
    payForm.setFieldsValue({ enabled: true, channel_type: 'im_b', sort_order: 0 });
    setPayModalVisible(true);
  };

  const openEditChannel = (ch: any) => {
    setEditingChannel(ch);
    payForm.setFieldsValue(ch);
    setPayModalVisible(true);
  };

  const handleChannelSubmit = async () => {
    try {
      const values = await payForm.validateFields();
      if (editingChannel) {
        await paymentChannelAPI.update(editingChannel.id, values);
        message.success('支付通道已更新');
      } else {
        await paymentChannelAPI.create(values);
        message.success('支付通道已创建');
      }
      setPayModalVisible(false);
      fetchPayChannels();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '操作失败');
    }
  };

  const handleDeleteChannel = async (id: number) => {
    try {
      await paymentChannelAPI.delete(id);
      message.success('支付通道已删除');
      fetchPayChannels();
    } catch { message.error('删除失败'); }
  };

  useEffect(() => {
    fetchPayChannels();
  }, []);

  return {
    payChannels, payLoading, payModalVisible, setPayModalVisible,
    editingChannel, payForm,
    fetchPayChannels, openCreateChannel, openEditChannel,
    handleChannelSubmit, handleDeleteChannel,
  };
}
