/**
 * 团队详情（右侧卡片）— 标题栏 + Tab（基本信息 / 成员管理 / 数据统计）
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  Card, Space, Tag, Avatar, Button, Popconfirm, Tabs, Descriptions,
  Badge, Table, Empty, Spin, Row, Col, Statistic, Divider,
} from 'antd';
import {
  TeamOutlined, EditOutlined, DeleteOutlined, InfoCircleOutlined,
  UserAddOutlined, BarChartOutlined, CrownOutlined, ToolOutlined,
  UserOutlined, ExclamationCircleOutlined, StopOutlined,
} from '@ant-design/icons';
import { statusColorMap, statusTextMap, roleColorMap, roleTextMap, roleIconMap } from '../constants';
import type { Team, TeamMember } from '../../../types';

interface TeamStats {
  stations: number;
  devices: number;
  members: number;
  workorders_month: number;
  alarms_week: number;
}

interface TeamDetailProps {
  selectedTeam: Team | null;
  detailLoading: boolean;
  members: TeamMember[];
  membersLoading: boolean;
  memberColumns: any[];
  teamStats: TeamStats | null;
  onEditTeam: (team: Team) => void;
  onDeleteTeam: (id: number) => void;
  onOpenAddMember: () => void;
}

const TeamDetail: React.FC<TeamDetailProps> = ({
  selectedTeam, detailLoading,
  members, membersLoading, memberColumns, teamStats,
  onEditTeam, onDeleteTeam, onOpenAddMember,
}) => {
  const { t } = useTranslation();
  return (
    <Card size="small" style={{ minHeight: 400 }}>
      {detailLoading ? (
        <div style={{ textAlign: 'center', padding: 80 }}><Spin tip={t('app.loading')} /></div>
      ) : !selectedTeam ? (
        <Empty description={t('pages.teams.select_prompt')} style={{ paddingTop: 80 }} />
      ) : (
        <>
          {/* 标题栏 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <Space>
              <Avatar size={40} style={{ background: '#ff5a36' }} icon={<TeamOutlined />} />
              <div>
                <h3 style={{ margin: 0 }}>{selectedTeam.name}</h3>
                <Space>
                  {selectedTeam.code && <Tag color="blue">{selectedTeam.code}</Tag>}
                  <span style={{ color: '#999', fontSize: 12 }}>ID: {selectedTeam.id}</span>
                </Space>
              </div>
              <Tag color={statusColorMap[selectedTeam.status]}>{statusTextMap[selectedTeam.status]}</Tag>
            </Space>
            <Space>
              <Button
                icon={<EditOutlined />} size="small"
                onClick={() => onEditTeam(selectedTeam)}
              >
                编辑
              </Button>
              <Popconfirm title={t('pages.teams.confirm_delete')} onConfirm={() => onDeleteTeam(selectedTeam.id)}>
                <Button icon={<DeleteOutlined />} size="small" danger>{t('app.delete')}</Button>
              </Popconfirm>
            </Space>
          </div>

          {/* Tab 区域 */}
          <Tabs
            defaultActiveKey="info"
            items={[
              {
                key: 'info',
                label: <span><InfoCircleOutlined /> {t('pages.teams.basic_info')}</span>,
                children: (
                  <Descriptions bordered column={{ xs: 1, sm: 2 }} size="small">
                    <Descriptions.Item label={t('pages.teams.team_name')}>{selectedTeam.name}</Descriptions.Item>
                    <Descriptions.Item label={t('pages.teams.code')}>
                      {selectedTeam.code ? <Tag color="blue">{selectedTeam.code}</Tag> : '-'}
                    </Descriptions.Item>
                    <Descriptions.Item label={t('pages.teams.manager')}>{selectedTeam.manager_name || '-'}</Descriptions.Item>
                    <Descriptions.Item label="状态">
                      <Tag color={statusColorMap[selectedTeam.status]}>{statusTextMap[selectedTeam.status]}</Tag>
                    </Descriptions.Item>
                    <Descriptions.Item label={t('pages.teams.members')}>{selectedTeam.member_count || 0}</Descriptions.Item>
                    <Descriptions.Item label={t('pages.teams.stations')}>{selectedTeam.station_count || 0}</Descriptions.Item>
                    <Descriptions.Item label="创建时间">
                      {selectedTeam.created_at ? new Date(selectedTeam.created_at).toLocaleString('zh-CN') : '-'}
                    </Descriptions.Item>
                    <Descriptions.Item label="更新时间">
                      {selectedTeam.updated_at ? new Date(selectedTeam.updated_at).toLocaleString('zh-CN') : '-'}
                    </Descriptions.Item>
                    <Descriptions.Item label={t('app.description')} span={2}>
                      {selectedTeam.description || '暂无描述'}
                    </Descriptions.Item>
                  </Descriptions>
                ),
              },
              {
                key: 'members',
                label: <span><TeamOutlined /> {t('pages.teams.member_management')} <Badge count={members.length} style={{ marginLeft: 4 }} /></span>,
                children: (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                      <Space>
                        <span style={{ fontWeight: 500 }}>团队成员</span>
                        <Tag color="red"><CrownOutlined /> 管理员 ×{members.filter((m: TeamMember) => m.role === 'admin').length}</Tag>
                        <Tag color="blue"><ToolOutlined /> 工程师 ×{members.filter((m: TeamMember) => m.role === 'engineer').length}</Tag>
                        <Tag color="green"><UserOutlined /> 技术员 ×{members.filter((m: TeamMember) => m.role === 'technician').length}</Tag>
                      </Space>
                      <Button
                        type="primary" icon={<UserAddOutlined />} size="small"
                        onClick={onOpenAddMember}
                      >
                        添加成员
                      </Button>
                    </div>
                    <Table
                      dataSource={members}
                      columns={memberColumns}
                      rowKey={(r) => r.user_id || r.id}
                      loading={membersLoading}
                      pagination={false}
                      size="small"
                      locale={{ emptyText: <Empty description="暂无成员" /> }}
                    />
                  </div>
                ),
              },
              {
                key: 'stats',
                label: <span><BarChartOutlined /> {t('pages.teams.statistics')}</span>,
                children: teamStats ? (
                  <div>
                    <Row gutter={[16, 16]}>
                      <Col span={8}>
                        <Card size="small" style={{ textAlign: 'center' }}>
                          <Statistic title={t('pages.teams.related_stations')} value={teamStats.stations} suffix={t('pages.teams.station_suffix')}
                            valueStyle={{ color: '#ff5a36' }} prefix={<TeamOutlined />} />
                        </Card>
                      </Col>
                      <Col span={8}>
                        <Card size="small" style={{ textAlign: 'center' }}>
                          <Statistic title={t('pages.teams.related_devices')} value={teamStats.devices} suffix={t('pages.teams.device_suffix')}
                            valueStyle={{ color: '#722ed1' }} />
                        </Card>
                      </Col>
                      <Col span={8}>
                        <Card size="small" style={{ textAlign: 'center' }}>
                          <Statistic title={t('pages.teams.related_members')} value={teamStats.members} suffix={t('pages.teams.person_suffix')}
                            valueStyle={{ color: '#34a853' }} prefix={<UserOutlined />} />
                        </Card>
                      </Col>
                    </Row>
                    <Divider />
                    <Row gutter={[16, 16]}>
                      <Col span={12}>
                        <Card size="small" style={{ textAlign: 'center', background: '#fff7e6' }}>
                          <Statistic title={t('pages.teams.monthly_workorders')} value={teamStats.workorders_month} suffix={t('pages.teams.order_suffix')}
                            prefix={<ExclamationCircleOutlined style={{ color: '#fa8c16' }} />}
                            valueStyle={{ color: '#fa8c16' }} />
                        </Card>
                      </Col>
                      <Col span={12}>
                        <Card size="small" style={{ textAlign: 'center', background: '#fff1f0' }}>
                          <Statistic title={t('pages.teams.weekly_alarms')} value={teamStats.alarms_week} suffix={t('pages.teams.alarm_suffix')}
                            prefix={<StopOutlined style={{ color: '#ea4335' }} />}
                            valueStyle={{ color: '#ea4335' }} />
                        </Card>
                      </Col>
                    </Row>
                    <Divider />
                    <Card size="small" title="成员角色分布">
                      <Row gutter={16}>
                        {Object.entries(roleTextMap).map(([key, label]) => {
                          const count = members.filter((m: TeamMember) => m.role === key).length;
                          const pct = members.length ? Math.round(count / members.length * 100) : 0;
                          return (
                            <Col span={8} key={key} style={{ textAlign: 'center' }}>
                              <div style={{ fontSize: 28, marginBottom: 4 }}>{roleIconMap[key]}</div>
                              <div style={{ fontWeight: 500 }}>{label}</div>
                              <div style={{ fontSize: 24, color: roleColorMap[key] === 'red' ? '#ea4335' : roleColorMap[key] === 'blue' ? '#ff5a36' : '#34a853' }}>
                                {count}
                              </div>
                              <div style={{ color: '#999', fontSize: 12 }}>占比 {pct}%</div>
                            </Col>
                          );
                        })}
                      </Row>
                    </Card>
                  </div>
                ) : <Empty />,
              },
            ]}
          />
        </>
      )}
    </Card>
  );
};

export default TeamDetail;
