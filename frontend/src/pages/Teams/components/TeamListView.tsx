/**
 * 团队列表（左侧卡片）— 搜索筛选 + 团队列表
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Button, Space, Input, Select, List, Tag, Avatar, Switch, Empty } from 'antd';
import { PlusOutlined, ReloadOutlined, SearchOutlined, TeamOutlined } from '@ant-design/icons';
import { statusColorMap, statusTextMap } from '../constants';
import type { Team } from '../../../types';

interface TeamListViewProps {
  teams: Team[];
  loading: boolean;
  searchText: string;
  onSearchChange: (v: string) => void;
  statusFilter: string;
  onStatusFilterChange: (v: string) => void;
  selectedTeamId: number | null;
  onSelectTeam: (id: number) => void;
  onToggleStatus: (team: Team) => void;
  onAddTeam: () => void;
  onRefresh: () => void;
}

const TeamListView: React.FC<TeamListViewProps> = ({
  teams, loading,
  searchText, onSearchChange,
  statusFilter, onStatusFilterChange,
  selectedTeamId, onSelectTeam, onToggleStatus, onAddTeam, onRefresh,
}) => {
  const { t } = useTranslation();
  return (
    <Card
      title={t('pages.teams.team_list')}
      size="small"
      extra={
        <Space size={4}>
          <Button
            type="primary" icon={<PlusOutlined />} size="small"
            onClick={onAddTeam}
          >
            新增
          </Button>
          <Button icon={<ReloadOutlined />} size="small" onClick={onRefresh} />
        </Space>
      }
    >
      <Space style={{ marginBottom: 12 }} wrap>
        <Input
          placeholder={t('pages.teams.search_placeholder')}
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={e => onSearchChange(e.target.value)}
          style={{ width: 160 }}
          size="small"
          allowClear
        />
        <Select value={statusFilter} onChange={onStatusFilterChange} size="small" style={{ width: 100 }}>
          <Select.Option value="all">{t('pages.teams.filter_all')}</Select.Option>
          <Select.Option value="active">{t('pages.teams.status_active')}</Select.Option>
          <Select.Option value="inactive">{t('pages.teams.status_inactive')}</Select.Option>
        </Select>
      </Space>
      <div style={{ maxHeight: 'calc(100vh - 340px)', overflowY: 'auto' }}>
        <List
          dataSource={teams}
          loading={loading}
          size="small"
          renderItem={(item: Team) => (
            <List.Item
              style={{
                cursor: 'pointer',
                background: selectedTeamId === item.id ? '#fef0ed' : undefined,
                padding: '8px 12px',
                borderRadius: 6,
              }}
              onClick={() => onSelectTeam(item.id)}
              actions={[
                <Switch
                  key="sw" size="small"
                  checked={item.status === 'active'}
                  onChange={() => onToggleStatus(item)}
                  onClick={(_, e) => e.stopPropagation()}
                />,
              ]}
            >
              <List.Item.Meta
                avatar={<Avatar size="small" style={{ background: '#ff5a36' }} icon={<TeamOutlined />} />}
                title={
                  <Space>
                    <span>{item.name}</span>
                    {item.code && <Tag color="blue" style={{ fontSize: 10 }}>{item.code}</Tag>}
                    <Tag color={statusColorMap[item.status]} style={{ fontSize: 10 }}>
                      {statusTextMap[item.status]}
                    </Tag>
                  </Space>
                }
                description={
                  <span style={{ fontSize: 12, color: '#999' }}>
                    {item.code ? `${item.code} · ` : ''}{item.member_count || 0}人 · {item.station_count || 0}站
                  </span>
                }
              />
            </List.Item>
          )}
          locale={{ emptyText: <Empty description={t('pages.teams.no_teams')} /> }}
        />
      </div>
    </Card>
  );
};

export default TeamListView;
