/**
 * 网关管理页面 — 数据与交互逻辑 Hook
 *
 * 封装：网关/SN码/固件/升级任务四类资源的按 Tab 懒加载、
 * SN 码生成、网关新增/编辑保存。
 */
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Form, message } from 'antd';
import { gatewayAPI } from '../../../api';
import type { Gateway } from '../../../types';

export function useGateways() {
  const { t } = useTranslation();
  const [gateways, setGateways] = useState<Gateway[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('gateways');
  const [modalVisible, setModalVisible] = useState(false);
  const [form] = Form.useForm();
  const [error, setError] = useState<string | null>(null);

  // SN码管理状态
  const [snCodes, setSnCodes] = useState<Gateway[]>([]);
  const [snLoading, setSnLoading] = useState(false);
  const [snError, setSnError] = useState<string | null>(null);

  // SN生成弹窗状态
  const [snGenerateModalVisible, setSnGenerateModalVisible] = useState(false);
  const [snGenerateForm] = Form.useForm();

  // 固件管理状态
  const [firmware, setFirmware] = useState<Gateway[]>([]);
  const [fwLoading, setFwLoading] = useState(false);
  const [fwError, setFwError] = useState<string | null>(null);

  // 升级任务状态
  const [upgradeTasks, setUpgradeTasks] = useState<Gateway[]>([]);
  const [taskLoading, setTaskLoading] = useState(false);
  const [taskError, setTaskError] = useState<string | null>(null);

  // 编辑状态
  const [editingGateway, setEditingGateway] = useState<Gateway | null>(null);

  // 加载网关列表
  const loadGateways = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await gatewayAPI.list();
      setGateways(Array.isArray(data) ? data : data.items || []);
    } catch (err: unknown) {
      const msg = (err as any)?.response?.data?.message || (err as any)?.message || '加载网关列表失败';
      setError(msg);
      message.error(t('pages.gateways.load_failed'));
    } finally {
      setLoading(false);
    }
  };

  // 加载SN码列表
  const loadSnCodes = async () => {
    setSnLoading(true);
    setSnError(null);
    try {
      const { data } = await gatewayAPI.sn();
      setSnCodes(Array.isArray(data) ? data : data.items || []);
    } catch (err: unknown) {
      const msg = (err as any)?.response?.data?.message || (err as any)?.message || '加载SN码列表失败';
      setSnError(msg);
      message.error(t('pages.gateways.sn_load_failed'));
    } finally {
      setSnLoading(false);
    }
  };

  // 加载固件列表
  const loadFirmware = async () => {
    setFwLoading(true);
    setFwError(null);
    try {
      const { data } = await gatewayAPI.firmware();
      setFirmware(Array.isArray(data) ? data : data.items || []);
    } catch (err: unknown) {
      const msg = (err as any)?.response?.data?.message || (err as any)?.message || '加载固件列表失败';
      setFwError(msg);
      message.error(t('pages.gateways.fw_load_failed'));
    } finally {
      setFwLoading(false);
    }
  };

  // 加载升级任务
  const loadUpgradeTasks = async () => {
    setTaskLoading(true);
    setTaskError(null);
    try {
      const { data } = await gatewayAPI.upgradeTasks();
      setUpgradeTasks(Array.isArray(data) ? data : data.items || []);
    } catch (err: unknown) {
      const msg = (err as any)?.response?.data?.message || (err as any)?.message || '加载升级任务失败';
      setTaskError(msg);
      message.error(t('pages.gateways.task_load_failed'));
    } finally {
      setTaskLoading(false);
    }
  };

  // Tab切换时加载对应数据
  useEffect(() => {
    switch (activeTab) {
      case 'gateways': loadGateways(); break;
      case 'sn': loadSnCodes(); break;
      case 'firmware': loadFirmware(); break;
      case 'tasks': loadUpgradeTasks(); break;
    }
  }, [activeTab]);

  // 打开SN生成弹窗
  const openSnGenerateModal = () => {
    snGenerateForm.resetFields();
    snGenerateForm.setFieldsValue({ count: 10, region: 'HN', model: 'TL-GW-100' });
    setSnGenerateModalVisible(true);
  };

  // 生成SN码（带区域参数）
  const handleGenerateSn = async () => {
    try {
      const values = await snGenerateForm.validateFields();
      const res = await gatewayAPI.generateSn({
        count: values.count,
        model: values.model,
        region: values.region,
      });
      message.success(res.data.message || `SN码生成成功 (区域: ${values.region})`);
      setSnGenerateModalVisible(false);
      loadSnCodes();
    } catch (err: unknown) {
      if ((err as any)?.errorFields) return;  // 表单验证失败
      message.error((err as any)?.response?.data?.message || '生成SN码失败');
    }
  };

  // 保存网关（新增/编辑）
  const handleSaveGateway = async () => {
    try {
      await form.validateFields();
      const values = form.getFieldsValue();
      if (editingGateway) {
        await gatewayAPI.update(editingGateway.id, values);
        message.success(t('pages.gateways.update_success'));
      } else {
        await gatewayAPI.create(values);
        message.success(t('pages.gateways.create_success'));
      }
      setModalVisible(false);
      form.resetFields();
      setEditingGateway(null);
      loadGateways();
    } catch {
      // 表单验证失败
    }
  };

  // 打开新增/编辑网关弹窗
  const openCreateGateway = () => {
    setEditingGateway(null);
    form.resetFields();
    setModalVisible(true);
  };

  const openEditGateway = (record: Gateway) => {
    setEditingGateway(record);
    setModalVisible(true);
  };

  // 关闭新增/编辑网关弹窗并复位
  const cancelEditGateway = () => {
    setModalVisible(false);
    form.resetFields();
    setEditingGateway(null);
  };

  // 删除网关
  const handleDeleteGateway = async (record: Gateway) => {
    try {
      await gatewayAPI.delete(record.id);
      message.success(t('pages.gateways.delete_success'));
      loadGateways();
    } catch {
      message.error(t('pages.gateways.delete_failed'));
    }
  };

  return {
    t,
    // 网关
    gateways, loading, error,
    // SN码
    snCodes, snLoading, snError,
    // 固件
    firmware, fwLoading, fwError,
    // 升级任务
    upgradeTasks, taskLoading, taskError,
    // Tab
    activeTab, setActiveTab,
    // 弹窗
    modalVisible, setModalVisible,
    snGenerateModalVisible, setSnGenerateModalVisible,
    editingGateway,
    form, snGenerateForm,
    // 操作
    loadGateways, loadSnCodes, loadFirmware, loadUpgradeTasks,
    openSnGenerateModal, handleGenerateSn, handleSaveGateway,
    openCreateGateway, openEditGateway, handleDeleteGateway, cancelEditGateway,
  };
}
