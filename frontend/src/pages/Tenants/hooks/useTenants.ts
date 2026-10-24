/**
 * 运维团队管理 — 主页面数据 Hook
 *
 * 封装租户列表/统计拉取、搜索防抖、CRUD 操作与 Modal/Drawer 状态。
 * 支持 TeamType 层级拆分：从 URL query param 读取 type（ops_company / maintenance_team）。
 */
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { Form, message } from 'antd';
import { tenantAPI } from '../../../api';
import type { Tenant, TenantStats } from '../types';

export function useTenants() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  // 从 URL query param 读取团队类型（ops_company / maintenance_team）
  const teamType = searchParams.get('type') || '';

  // 运维团队（maintenance_team）需要选择所属运营公司；运营公司不需要
  const needsParentTeam = teamType === 'maintenance_team';

  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [selectedTenant, setSelectedTenant] = useState<Tenant | null>(null);
  const [editingTenant, setEditingTenant] = useState<Tenant | null>(null);
  const [searchText, setSearchText] = useState('');
  const [stats, setStats] = useState({ total: 0, active: 0, totalStations: 0, totalDevices: 0 });
  const [form] = Form.useForm();

  // 运营公司列表（用于运维团队表单"所属运营公司"下拉）
  const [opsCompanies, setOpsCompanies] = useState<Tenant[]>([]);

  // 根据 URL 路径确定当前 Tab
  const getActiveTab = () => {
    if (location.pathname.endsWith('/data')) return 'data';
    if (location.pathname.endsWith('/accounts')) return 'accounts';
    return 'list';
  };

  // Tab 切换时更新 URL（保留 query param）
  const onTabChange = (key: string) => {
    const q = teamType ? `?type=${teamType}` : '';
    if (key === 'list') navigate(`/tenants${q}`);
    else if (key === 'data') navigate(`/tenants/data${q}`);
    else if (key === 'accounts') navigate(`/tenants/accounts${q}`);
  };

  const fetchTenants = async (keyword?: string) => {
    setLoading(true);
    try {
      const params: { keyword?: string; type?: string } = {};
      if (keyword) params.keyword = keyword;
      if (teamType) params.type = teamType;
      const res = await tenantAPI.list(params);
      const data = res.data;
      const list = Array.isArray(data) ? data : (data?.items || data?.list || data?.data || []);
      setTenants(list);
    } catch (err) {
      message.error(t('pages.tenants.load_failed'));
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const res = await tenantAPI.stats();
      const data = res.data as TenantStats;
      setStats({
        total: data?.total || 0,
        active: data?.active || 0,
        totalStations: data?.total_stations || 0,
        totalDevices: data?.total_devices || 0,
      });
    } catch {
      // 静默处理：统计加载失败保留上次值
    }
  };

  // 拉取运营公司列表（用于运维团队表单的"所属运营公司"下拉）
  const fetchOpsCompanies = async () => {
    try {
      const res = await tenantAPI.list({ type: 'ops_company' });
      const data = res.data;
      const list = Array.isArray(data) ? data : (data?.items || data?.list || data?.data || []);
      setOpsCompanies(list);
    } catch {
      // 静默处理：下拉选项加载失败不阻塞主流程
    }
  };

  useEffect(() => {
    fetchTenants();
    fetchStats();
    if (needsParentTeam) fetchOpsCompanies();
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => { fetchTenants(searchText); }, 300);
    return () => clearTimeout(timer);
  }, [searchText]);

  // ---------- 操作方法 ----------

  const openEdit = (record: Tenant) => {
    setEditingTenant(record);
    form.setFieldsValue(record);
    setModalVisible(true);
  };

  const toggleStatus = async (record: Tenant) => {
    try {
      const newStatus = record.status === 'disabled' ? 'active' : 'disabled';
      await tenantAPI.update(record.id, { status: newStatus });
      message.success(t('pages.tenants.status_updated'));
      fetchTenants(searchText);
      fetchStats();
    } catch (err) {
      message.error(t('pages.tenants.status_update_failed'));
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await tenantAPI.delete(id);
      message.success(t('pages.tenants.delete_success'));
      fetchTenants(searchText);
      fetchStats();
    } catch (err) {
      message.error(t('pages.tenants.delete_failed'));
    }
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      // 新建时附带 type
      if (teamType && !editingTenant) {
        values.type = teamType;
      }
      // 运营公司不需要 parent_team_id
      if (!needsParentTeam) {
        delete values.parent_team_id;
      }
      try {
        if (editingTenant) {
          await tenantAPI.update(editingTenant.id, values);
          message.success(t('pages.tenants.update_success'));
        } else {
          await tenantAPI.create(values);
          message.success(t('pages.tenants.create_success'));
        }
        setModalVisible(false);
        form.resetFields();
        setEditingTenant(null);
        fetchTenants(searchText);
        fetchStats();
      } catch {
        message.error(editingTenant ? t('pages.tenants.update_failed') : t('pages.tenants.create_failed'));
      }
    } catch {
      // 静默处理：表单校验失败由 antd 字段提示覆盖
    }
  };

  return {
    t,
    tenants,
    loading,
    modalVisible,
    setModalVisible,
    drawerVisible,
    setDrawerVisible,
    selectedTenant,
    setSelectedTenant,
    editingTenant,
    setEditingTenant,
    searchText,
    setSearchText,
    stats,
    form,
    teamType,
    needsParentTeam,
    opsCompanies,
    fetchOpsCompanies,
    getActiveTab,
    onTabChange,
    fetchTenants,
    fetchStats,
    openEdit,
    toggleStatus,
    handleDelete,
    handleSave,
  };
}
