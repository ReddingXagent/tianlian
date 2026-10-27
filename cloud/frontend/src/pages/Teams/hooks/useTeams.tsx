/**
 * 团队管理页面 — 数据与交互逻辑 Hook
 *
 * 封装：团队列表/详情/成员拉取、搜索筛选、统计派生、
 * CRUD、成员增删改、状态切换、编码预览。
 */
import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Form, message, Switch, Tag, Button, Space, Tooltip, Popconfirm, Avatar, Select } from 'antd';
import {
  EditOutlined, DeleteOutlined, CrownOutlined, ToolOutlined, UserOutlined,
} from '@ant-design/icons';
import { teamAPI, userAPI } from '../../../api';
import type { Team, TeamMember, User } from '../../../types';

export function useTeams() {
  const { t } = useTranslation();
  /* ── 列表状态 ── */
  const [teams, setTeams] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  /* ── 详情状态 ── */
  const [selectedTeamId, setSelectedTeamId] = useState<number | null>(null);
  const [selectedTeam, setSelectedTeam] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [members, setMembers] = useState<any[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);

  /* ── 弹窗状态 ── */
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingTeam, setEditingTeam] = useState<any>(null);
  const [addMemberVisible, setAddMemberVisible] = useState(false);
  const [allUsers, setAllUsers] = useState<any[]>([]);
  const [form] = Form.useForm();
  const [memberForm] = Form.useForm();

  /* ── 编码预览 ── */
  const [previewCode, setPreviewCode] = useState<string>('');

  /* ── 加载团队列表 ── */
  const loadTeams = useCallback(async () => {
    setLoading(true);
    try {
      const res: any = await teamAPI.list();
      const list = (res?.data as any)?.items || res?.data || [];
      setTeams(list);
    } catch {
      message.error(t('pages.teams.load_failed'));
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadTeams(); }, [loadTeams]);

  /* ── 选中团队加载详情 ── */
  const selectTeam = useCallback(async (id: number) => {
    setSelectedTeamId(id);
    setDetailLoading(true);
    try {
      const res: { data: Team } = await teamAPI.get(id);
      setSelectedTeam(res.data || res);
    } catch {
      message.error('加载团队详情失败');
      setSelectedTeam(null);
    }
    setDetailLoading(false);
  }, []);

  /* ── 加载成员列表 ── */
  const loadMembers = useCallback(async (teamId: number) => {
    setMembersLoading(true);
    try {
      const res: any = await teamAPI.members(teamId);
      setMembers((res?.data as any)?.items || res?.data || []);
    } catch {
      // 成员接口可能返回空，静默处理
      setMembers([]);
    }
    setMembersLoading(false);
  }, []);

  /* ── 当选中团队变化时加载成员 ── */
  useEffect(() => {
    if (selectedTeamId) loadMembers(selectedTeamId);
  }, [selectedTeamId, loadMembers]);

  /* ── 筛选 ── */
  const filteredTeams = teams.filter((t: Team) => {
    const matchSearch = !searchText ||
      t.name?.toLowerCase().includes(searchText.toLowerCase()) ||
      t.code?.toLowerCase().includes(searchText.toLowerCase());
    const matchStatus = statusFilter === 'all' || t.status === statusFilter;
    return matchSearch && matchStatus;
  });

  /* ── 统计 ── */
  const stats = {
    total: teams.length,
    active: teams.filter((t: Team) => t.status === 'active').length,
    totalMembers: teams.reduce((sum: number, t: Team) => sum + (t.member_count || 0), 0),
  };

  /* ── 生成编码预览 ── */
  const generatePreviewCode = (region: string) => {
    // 预览格式: T + 区域码 + 示例序号
    return `T${region}0001`;
  };

  /* ── 区域变化时更新预览 ── */
  const handleRegionChange = (region: string) => {
    setPreviewCode(generatePreviewCode(region));
  };

  /* ── CRUD 操作 ── */
  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      if (editingTeam) {
        await teamAPI.update(editingTeam.id, values);
        message.success(t('pages.teams.update_success'));
      } else {
        // 新增团队，传入region参数
        const createData = {
          name: values.name,
          region: values.region || 'HN',
          leader_id: values.leader_id,
          description: values.description,
        };
        const res = await teamAPI.create(createData);
        message.success(`团队已创建，编码: ${(res as any)?.data?.code || '已生成'}`);
      }
      setEditModalVisible(false);
      form.resetFields();
      setPreviewCode('');
      loadTeams();
      if (selectedTeamId) selectTeam(selectedTeamId);
    } catch {
      message.error(editingTeam ? t('pages.teams.update_failed') : t('pages.teams.create_failed'));
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await teamAPI.delete(id);
      message.success(t('pages.teams.delete_success'));
      if (selectedTeamId === id) {
        setSelectedTeamId(null);
        setSelectedTeam(null);
      }
      loadTeams();
    } catch {
      message.error(t('pages.teams.delete_failed'));
    }
  };

  const handleToggleStatus = async (team: Team) => {
    const newStatus = team.status === 'active' ? 'inactive' : 'active';
    try {
      await teamAPI.update(team.id, { ...team, status: newStatus });
      message.success(newStatus === 'active' ? t('pages.teams.enabled') : t('pages.teams.disabled'));
      loadTeams();
      if (selectedTeamId === team.id) selectTeam(team.id);
    } catch {
      message.error(t('pages.teams.toggle_failed'));
    }
  };

  /* ── 成员操作 ── */
  const handleAddMember = async () => {
    if (!selectedTeamId) return;
    try {
      const values = await memberForm.validateFields();
      await teamAPI.addMember(selectedTeamId, values);
      message.success(t('pages.teams.member_added'));
      setAddMemberVisible(false);
      memberForm.resetFields();
      loadMembers(selectedTeamId);
      loadTeams();
    } catch {
      message.error(t('pages.teams.member_add_failed'));
    }
  };

  const handleRemoveMember = async (memberId: number) => {
    if (!selectedTeamId) return;
    try {
      await teamAPI.removeMember(selectedTeamId, memberId);
      message.success(t('pages.teams.member_removed'));
      loadMembers(selectedTeamId);
      loadTeams();
    } catch {
      message.error(t('pages.teams.member_remove_failed'));
    }
  };

  const handleChangeRole = async (memberId: number, newRole: string) => {
    if (!selectedTeamId) return;
    try {
      // 通过 addMember 更新角色（后端 upsert 语义）
      await teamAPI.addMember(selectedTeamId, { user_id: memberId, role: newRole });
      message.success(t('pages.teams.role_updated'));
      loadMembers(selectedTeamId);
    } catch {
      message.error(t('pages.teams.role_update_failed'));
    }
  };

  /* ── 打开添加成员弹窗 ── */
  const openAddMember = async () => {
    try {
      const res: any = await userAPI.list();
      setAllUsers((res?.data as any)?.items || res?.data || []);
    } catch {
      setAllUsers([]);
    }
    memberForm.resetFields();
    setAddMemberVisible(true);
  };

  /* ── 打开新增/编辑弹窗 ── */
  const openCreateTeam = () => {
    setEditingTeam(null);
    form.resetFields();
    form.setFieldsValue({ region: 'HN' });  // 默认HN
    setPreviewCode(generatePreviewCode('HN'));
    setEditModalVisible(true);
  };

  const openEditTeam = (team: Team) => {
    setEditingTeam(team);
    form.setFieldsValue(team);
    setEditModalVisible(true);
  };

  /* ── 列表列定义 ── */
  const columns = [
    {
      title: t('pages.teams.team_name'), dataIndex: 'name', key: 'name', width: 140, ellipsis: true,
      render: (name: string, record: Team) => (
        <Button type="link" size="small" onClick={() => selectTeam(record.id)} style={{ padding: 0 }}>
          {name}
        </Button>
      ),
    },
    { title: t('pages.teams.code'), dataIndex: 'code', key: 'code', width: 100, ellipsis: true,
      render: (code: string) => code ? <Tag color="blue">{code}</Tag> : '-'
    },
    { title: t('pages.teams.manager'), dataIndex: 'manager_name', key: 'manager_name', width: 80 },
    {
      title: t('pages.teams.members'), dataIndex: 'member_count', key: 'member_count', width: 60,
      sorter: (a: Team, b: Team) => (a.member_count || 0) - (b.member_count || 0),
    },
    {
      title: t('pages.teams.stations'), dataIndex: 'station_count', key: 'station_count', width: 60,
      sorter: (a: Team, b: Team) => (a.station_count || 0) - (b.station_count || 0),
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 70,
      render: (status: string, record: Team) => (
        <Switch
          size="small"
          checked={status === 'active'}
          onChange={() => handleToggleStatus(record)}
          checkedChildren="启"
          unCheckedChildren="停"
        />
      ),
    },
    {
      title: t('app.action'), key: 'action', width: 80,
      render: (_: unknown, record: Team) => (
        <Space size={4}>
          <Tooltip title={t('app.edit')}>
            <Button
              icon={<EditOutlined />} size="small"
              onClick={() => openEditTeam(record)}
            />
          </Tooltip>
          <Popconfirm title={t('pages.teams.confirm_delete')} onConfirm={() => handleDelete(record.id)}>
            <Tooltip title={t('app.delete')}>
              <Button icon={<DeleteOutlined />} size="small" danger />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  /* ── 成员表格列 ── */
  const memberColumns = [
    {
      title: t('pages.teams.members'), key: 'name', width: 150,
      render: (_: unknown, r: TeamMember) => (
        <Space>
          <Avatar size="small" icon={<UserOutlined />} />
          <span>{r.real_name || r.username || `用户${r.user_id}`}</span>
        </Space>
      ),
    },
    {
      title: t('pages.teams.role'), dataIndex: 'role', key: 'role', width: 160,
      render: (role: string, record: TeamMember) => (
        <Select
          value={role}
          size="small"
          style={{ width: 130 }}
          onChange={(v) => handleChangeRole(record.user_id || record.id, v)}
        >
          <Select.Option value="admin">
            <Space><CrownOutlined style={{ color: 'red' }} />管理员</Space>
          </Select.Option>
          <Select.Option value="engineer">
            <Space><ToolOutlined style={{ color: '#ff5a36' }} />工程师</Space>
          </Select.Option>
          <Select.Option value="technician">
            <Space><UserOutlined style={{ color: '#34a853' }} />技术员</Space>
          </Select.Option>
        </Select>
      ),
    },
    {
      title: t('pages.teams.joined_at'), dataIndex: 'joined_at', key: 'joined_at', width: 160,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (s: string) => <Tag color={s === 'active' || !s ? 'green' : 'default'}>{s === 'active' || !s ? t('pages.teams.status_active') : t('pages.teams.status_offline')}</Tag>,
    },
    {
      title: t('app.action'), key: 'action', width: 60,
      render: (_: unknown, record: TeamMember) => (
        <Popconfirm title={t('pages.teams.confirm_remove_member')} onConfirm={() => handleRemoveMember(record.user_id || record.id)}>
          <Tooltip title="移除">
            <Button icon={<DeleteOutlined />} size="small" danger type="text" />
          </Tooltip>
        </Popconfirm>
      ),
    },
  ];

  /* ── 数据统计 Tab 的模拟数据（后端无统计API时用列表数据推算） ── */
  const teamStats = selectedTeam ? {
    stations: selectedTeam.station_count || 0,
    devices: selectedTeam.device_count || Math.floor((selectedTeam.station_count || 0) * 3),
    members: members.length,
    workorders_month: selectedTeam.workorder_count || 0,
    alarms_week: selectedTeam.alarm_count || 0,
  } : null;

  return {
    t,
    // 列表
    filteredTeams, loading, stats,
    searchText, setSearchText,
    statusFilter, setStatusFilter,
    // 详情
    selectedTeamId, selectedTeam, detailLoading,
    members, membersLoading, memberColumns, teamStats,
    // 弹窗
    editModalVisible, setEditModalVisible,
    editingTeam,
    addMemberVisible, setAddMemberVisible,
    allUsers,
    form, memberForm,
    previewCode, setPreviewCode,
    // 操作
    loadTeams, selectTeam,
    handleSave, handleDelete, handleToggleStatus,
    handleAddMember, openAddMember,
    handleRegionChange,
    openCreateTeam, openEditTeam,
  };
}
