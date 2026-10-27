/**
 * 天链 V3 - 系统配置：权限配置 (RBAC) 数据 hook
 */
import { useState, useMemo, useEffect } from 'react';
import { Form, message } from 'antd';
import { ApartmentOutlined } from '@ant-design/icons';
import type { DataNode } from 'antd/es/tree';
import { rbacAPI } from '../../../api';
import { RESOURCE_LABEL } from '../constants';
import type { PermissionItem, RoleItem } from '../types';

export function useRbac() {
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [allPermissions, setAllPermissions] = useState<PermissionItem[]>([]);
  const [rbacLoading, setRbacLoading] = useState(false);
  const [roleModalVisible, setRoleModalVisible] = useState(false);
  const [editingRole, setEditingRole] = useState<RoleItem | null>(null);
  const [roleForm] = Form.useForm();

  const fetchRoles = async () => {
    setRbacLoading(true);
    try {
      const res: any = await rbacAPI.roles();
      const data = res?.data || res;
      setRoles(data.items || []);
    } catch { message.error('获取角色列表失败'); }
    finally { setRbacLoading(false); }
  };

  const fetchPermissions = async () => {
    try {
      const res: any = await rbacAPI.permissions();
      const data = res?.data || res;
      setAllPermissions(data.items || []);
    } catch { /* ignore */ }
  };

  const permissionGroups = useMemo(() => {
    const groups: Record<string, PermissionItem[]> = {};
    allPermissions.forEach(p => {
      const group = p.resource || 'other';
      if (!groups[group]) groups[group] = [];
      groups[group].push(p);
    });
    return groups;
  }, [allPermissions]);

  // 权限树形图数据
  const permissionTreeData = useMemo((): DataNode[] => {
    return Object.entries(permissionGroups).map(([resource, perms]) => ({
      title: RESOURCE_LABEL[resource] || resource,
      key: resource,
      icon: <ApartmentOutlined />,
      children: perms.map(p => ({
        title: <span>{p.label} <code style={{ fontSize: 11, color: '#999' }}>({p.name})</code></span>,
        key: p.name,
        isLeaf: true,
      })),
    }));
  }, [permissionGroups]);

  const openCreateRole = () => {
    setEditingRole(null);
    roleForm.resetFields();
    setRoleModalVisible(true);
  };

  const openEditRole = (role: RoleItem) => {
    setEditingRole(role);
    roleForm.setFieldsValue({
      name: role.name,
      display_name: role.display_name,
      description: role.description,
      permissions: role.permissions,
    });
    setRoleModalVisible(true);
  };

  const handleRoleSubmit = async () => {
    try {
      const values = await roleForm.validateFields();
      if (editingRole) {
        await rbacAPI.updateRole(editingRole.id, {
          display_name: values.display_name,
          description: values.description,
          permissions: values.permissions || [],
        });
        message.success('角色更新成功');
      } else {
        await rbacAPI.createRole({
          name: values.name,
          display_name: values.display_name,
          description: values.description,
          permissions: values.permissions || [],
        });
        message.success('角色创建成功');
      }
      setRoleModalVisible(false);
      fetchRoles();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '操作失败');
    }
  };

  const handleDeleteRole = async (role: RoleItem) => {
    try {
      await rbacAPI.deleteRole(role.id);
      message.success(`角色 ${role.display_name} 已删除`);
      fetchRoles();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '删除失败');
    }
  };

  useEffect(() => {
    fetchRoles();
    fetchPermissions();
  }, []);

  return {
    roles, allPermissions, rbacLoading,
    roleModalVisible, setRoleModalVisible, editingRole,
    roleForm, permissionGroups, permissionTreeData,
    fetchRoles, fetchPermissions,
    openCreateRole, openEditRole, handleRoleSubmit, handleDeleteRole,
  };
}
