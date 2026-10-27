/**
 * 天链 V3 - 团队管理页面（增强版 + 编码重构）
 * 左右布局：左侧团队列表，右侧团队详情（含Tab：基本信息、成员管理、数据统计）
 *
 * 重构：新增团队时选择区域，自动生成编码
 */
import React from 'react';
import { Row, Col } from 'antd';
import { useTeams } from './hooks/useTeams';
import TeamStatsCards from './components/TeamStatsCards';
import TeamListView from './components/TeamListView';
import TeamDetail from './components/TeamDetail';
import TeamEditModal from './components/TeamEditModal';
import AddMemberModal from './components/AddMemberModal';

const TeamsPage: React.FC = () => {
  const {
    filteredTeams, loading, stats,
    searchText, setSearchText,
    statusFilter, setStatusFilter,
    selectedTeamId, selectedTeam, detailLoading,
    members, membersLoading, memberColumns, teamStats,
    editModalVisible, setEditModalVisible,
    editingTeam,
    addMemberVisible, setAddMemberVisible,
    allUsers,
    form, memberForm,
    previewCode, setPreviewCode,
    loadTeams, selectTeam,
    handleSave, handleDelete, handleToggleStatus,
    handleAddMember, openAddMember,
    handleRegionChange,
    openCreateTeam, openEditTeam,
  } = useTeams();

  return (
    <div className="page-container">
      {/* 统计卡片 */}
      <TeamStatsCards stats={stats} />

      {/* 主体：左右布局 */}
      <Row gutter={16}>
        {/* 左侧：团队列表 */}
        <Col xs={24} lg={10} xl={8}>
          <TeamListView
            teams={filteredTeams}
            loading={loading}
            searchText={searchText}
            onSearchChange={setSearchText}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
            selectedTeamId={selectedTeamId}
            onSelectTeam={selectTeam}
            onToggleStatus={handleToggleStatus}
            onAddTeam={openCreateTeam}
            onRefresh={loadTeams}
          />
        </Col>

        {/* 右侧：团队详情 */}
        <Col xs={24} lg={14} xl={16}>
          <TeamDetail
            selectedTeam={selectedTeam}
            detailLoading={detailLoading}
            members={members}
            membersLoading={membersLoading}
            memberColumns={memberColumns}
            teamStats={teamStats}
            onEditTeam={openEditTeam}
            onDeleteTeam={handleDelete}
            onOpenAddMember={openAddMember}
          />
        </Col>
      </Row>

      {/* 编辑/新增弹窗 */}
      <TeamEditModal
        open={editModalVisible}
        editingTeam={editingTeam}
        form={form}
        previewCode={previewCode}
        allUsers={allUsers}
        onRegionChange={handleRegionChange}
        onCancel={() => {
          setEditModalVisible(false);
          form.resetFields();
          setPreviewCode('');
        }}
        onSave={handleSave}
      />

      {/* 添加成员弹窗 */}
      <AddMemberModal
        open={addMemberVisible}
        memberForm={memberForm}
        allUsers={allUsers}
        onCancel={() => setAddMemberVisible(false)}
        onAdd={handleAddMember}
      />
    </div>
  );
};

export default TeamsPage;
