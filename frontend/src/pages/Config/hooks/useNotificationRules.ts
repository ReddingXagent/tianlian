/**
 * 天链 V3 - 系统配置：通知规则数据 hook
 */
import { useState, useEffect } from 'react';
import { Form, message } from 'antd';
import { notificationRuleAPI } from '../../../api';
import type { NotificationRule } from '../types';

export function useNotificationRules() {
  const [rules, setRules] = useState<NotificationRule[]>([]);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [ruleModalVisible, setRuleModalVisible] = useState(false);
  const [editingRule, setEditingRule] = useState<NotificationRule | null>(null);
  const [ruleForm] = Form.useForm();

  const fetchRules = async () => {
    setRulesLoading(true);
    try {
      const res: any = await notificationRuleAPI.list();
      const data = res?.data || res;
      setRules(Array.isArray(data) ? data : []);
    } catch { message.error('获取通知规则失败'); }
    finally { setRulesLoading(false); }
  };

  const openCreateRule = () => {
    setEditingRule(null);
    ruleForm.resetFields();
    ruleForm.setFieldsValue({ enabled: true });
    setRuleModalVisible(true);
  };

  const openEditRule = (rule: NotificationRule) => {
    setEditingRule(rule);
    ruleForm.setFieldsValue(rule);
    setRuleModalVisible(true);
  };

  const handleRuleSubmit = async () => {
    try {
      const values = await ruleForm.validateFields();
      if (editingRule) {
        await notificationRuleAPI.update(editingRule.id, values);
        message.success('规则更新成功');
      } else {
        await notificationRuleAPI.create(values);
        message.success('规则创建成功');
      }
      setRuleModalVisible(false);
      fetchRules();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '操作失败');
    }
  };

  const handleDeleteRule = async (id: number) => {
    try {
      await notificationRuleAPI.delete(id);
      message.success('规则已删除');
      fetchRules();
    } catch { message.error('删除失败'); }
  };

  const handleToggleRule = async (id: number) => {
    try {
      await notificationRuleAPI.toggle(id);
      message.success('状态已切换');
      fetchRules();
    } catch { message.error('切换失败'); }
  };

  useEffect(() => {
    fetchRules();
  }, []);

  return {
    rules, rulesLoading, ruleModalVisible, setRuleModalVisible,
    editingRule, setEditingRule, ruleForm,
    fetchRules, openCreateRule, openEditRule, handleRuleSubmit,
    handleDeleteRule, handleToggleRule,
  };
}
