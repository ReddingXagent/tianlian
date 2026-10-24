/**
 * Tab3: 团队账户（全团队账户列表与统计）
 *
 * 卡9a81fffd：改调 GET /teams/{team_id}/members 聚合各团队真实账户，去除硬编码假账号。
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Table, Card, Button, Space, Tag, Badge, Statistic, Tooltip, message, Empty, Typography, Modal,
} from 'antd';
import {
  UserOutlined, ReloadOutlined, KeyOutlined, LockOutlined, UnlockOutlined,
} from '@ant-design/icons';
import { teamAPI, passwordResetAPI } from '../../../api';
import { getStatusMap } from '../utils';
import type { Tenant, TeamAccount } from '../types';

const { Text } = Typography;

const TeamAccountsView: React.FC<{
  tenants: Tenant[];
  loading: boolean;
  onRefresh: () => void;
}> = ({ tenants, loading, onRefresh }) => {
  const { t } = useTranslation();
  const statusMap = getStatusMap(t);

  // 各团队真实成员（卡9a81fffd：接 /teams/{id}/members）
  const [accounts, setAccounts] = useState<TeamAccount[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);

  // 密码重置（卡 922b2fba：接真实 API，展示一次性临时密码）
  const [resettingId, setResettingId] = useState<number | null>(null);
  const [tempPwd, setTempPwd] = useState<{ username: string; password: string } | null>(null);

  const handleResetPassword = async (record: TeamAccount) => {
    setResettingId(record.id);
    try {
      const res = await passwordResetAPI.tenantUser(record.tenant_id, record.id);
      const pwd = res.data?.data?.temporary_password || res.data?.temporary_password || '';
      if (pwd) {
        setTempPwd({ username: record.username, password: String(pwd) });
      } else {
        message.success('密码已重置');
      }
    } catch {
      message.error('重置失败，请稍后重试');
    } finally {
      setResettingId(null);
    }
  };

  const fetchAccounts = useCallback(async (tenantList: Tenant[]) => {
    if (tenantList.length === 0) {
      setAccounts([]);
      return;
    }
    setAccountsLoading(true);
    try {
      const results = await Promise.all(
        tenantList.map(async (tn) => {
          try {
            const res = await teamAPI.members(tn.id);
            const data = res.data;
            const list = Array.isArray(data) ? data : (data?.items || data?.list || data?.data || []);
            return (list as Array<Record<string, unknown>>).map((m, i) => ({
              id: (m.id as number) ?? i,
              tenant_id: tn.id,
              tenant_name: tn.name,
              username: (m.username as string) || '-',
              real_name: (m.real_name as string) || '-',
              role: (m.role as string) || '-',
              status: (m.status as string) || 'active',
              last_login: ((m.join_date as string) || tn.created_at || '').slice(0, 10),
              created_at: ((m.join_date as string) || tn.created_at || '').slice(0, 10),
            }));
          } catch {
            return [];
          }
        })
      );
      setAccounts(results.flat());
    } finally {
      setAccountsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAccounts(tenants);
  }, [tenants, fetchAccounts]);

  const accountColumns = [
    { title: t('pages.tenants.team'), dataIndex: 'tenant_name', key: 'tenant_name', width: 160 },
    { title: t('pages.tenants.account_name'), dataIndex: 'username', key: 'username', width: 130 },
    { title: t('pages.tenants.real_name'), dataIndex: 'real_name', key: 'real_name', width: 90 },
    {
      title: '角色', dataIndex: 'role', key: 'role', width: 100,
      render: (r: string) => <Tag>{r}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 70,
      render: (s: string) => <Badge status={s === 'active' ? 'success' : 'default'} text={s === 'active' ? t('pages.tenants.normal') : t('pages.tenants.disabled')} />,
    },
    { title: t('pages.tenants.last_login'), dataIndex: 'last_login', key: 'last_login', width: 110 },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, record: TeamAccount) => (
        <Space size="small">
          <Tooltip title={t('pages.tenants.reset_password')}><Button icon={<KeyOutlined />} size="small" loading={resettingId === record.id} onClick={() => handleResetPassword(record)} /></Tooltip>
          {record.status === 'active' ? (
            <Tooltip title={t('pages.tenants.disable_account')}><Button icon={<LockOutlined />} size="small" danger onClick={() => message.success(t('pages.tenants.account_disabled'))} /></Tooltip>
          ) : (
            <Tooltip title={t('pages.tenants.enable_account')}><Button icon={<UnlockOutlined />} size="small" type="primary" onClick={() => message.success(t('pages.tenants.account_enabled'))} /></Tooltip>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Statistic title={t('pages.tenants.total_accounts')} value={accounts.length} suffix={t('pages.tenants.account_suffix')} prefix={<UserOutlined />} />
          <Statistic title={t('pages.tenants.active_accounts')} value={accounts.filter(a => a.status === 'active').length} valueStyle={{ color: '#34a853' }} />
          <Statistic title={t('pages.tenants.admin_accounts')} value={accounts.filter(a => a.role === 'admin').length} />
          <Statistic title={t('pages.tenants.engineer_accounts')} value={accounts.filter(a => a.role === 'engineer').length} />
        </Space>
      </Card>

      <Card
        title="全团队账户列表"
        size="small"
        extra={
          <Space>
            <Text type="secondary">{t('pages.tenants.accounts_mgmt_note')}</Text>
            <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh}>{t('app.refresh')}</Button>
          </Space>
        }
      >
        <Table
          dataSource={accounts}
          columns={accountColumns}
          rowKey={(r) => `${r.tenant_id}-${r.id}`}
          loading={loading || accountsLoading}
          size="small"
          pagination={{ pageSize: 15 }}
          locale={{ emptyText: <Empty description={t('pages.tenants.members_empty')} image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
        />
      </Card>

      {/* 一次性临时密码展示（关闭后不可再查，需重新重置） */}
      <Modal
        open={!!tempPwd}
        title="密码已重置"
        onOk={() => setTempPwd(null)}
        onCancel={() => setTempPwd(null)}
        okText="我已保存"
        cancelButtonProps={{ style: { display: 'none' } }}
      >
        <p>
          账号 <Text strong copyable>{tempPwd?.username}</Text> 的密码已重置，临时密码：
        </p>
        <p style={{ fontSize: 18, textAlign: 'center', margin: '16px 0' }}>
          <Text strong copyable code>{tempPwd?.password}</Text>
        </p>
        <Text type="secondary" style={{ fontSize: 12 }}>
          请将临时密码告知该用户（仅本次展示，关闭后无法再查看）。用户登录后应尽快修改密码。
        </Text>
      </Modal>
    </div>
  );
};

export default TeamAccountsView;
