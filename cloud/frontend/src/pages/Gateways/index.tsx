/**
 * 天链 V3 - 网关管理页面（编码重构）
 *
 * 修改记录：
 * - 2026-05-03 增强：Tabs items API (antd v5), 真实API调用, 错误处理, 空状态
 * - 2026-06-06 重构：SN生成增加区域选择，使用结构化编码
 */
import React from 'react';
import { Card, Tabs, Tag } from 'antd';
import { useGateways } from './hooks/useGateways';
import GatewaysTab from './components/GatewaysTab';
import SnCodesTab from './components/SnCodesTab';
import FirmwareTab from './components/FirmwareTab';
import UpgradeTasksTab from './components/UpgradeTasksTab';
import GatewayEditModal from './components/GatewayEditModal';
import GenerateSnModal from './components/GenerateSnModal';

const GatewayPage: React.FC = () => {
  const {
    t,
    gateways, loading, error,
    snCodes, snLoading, snError,
    firmware, fwLoading, fwError,
    upgradeTasks, taskLoading, taskError,
    activeTab, setActiveTab,
    modalVisible,
    snGenerateModalVisible, setSnGenerateModalVisible,
    editingGateway,
    form, snGenerateForm,
    loadGateways, loadSnCodes, loadFirmware, loadUpgradeTasks,
    openSnGenerateModal, handleGenerateSn, handleSaveGateway,
    openCreateGateway, openEditGateway, handleDeleteGateway, cancelEditGateway,
  } = useGateways();

  // antd v5 Tabs items 格式
  const tabItems = [
    {
      key: 'gateways',
      label: t('pages.gateways.gateway_mgmt'),
      children: (
        <GatewaysTab
          gateways={gateways}
          loading={loading}
          error={error}
          onAdd={openCreateGateway}
          onRefresh={loadGateways}
          onEdit={openEditGateway}
          onDelete={handleDeleteGateway}
        />
      ),
    },
    {
      key: 'sn',
      label: t('pages.gateways.sn_mgmt'),
      children: (
        <SnCodesTab
          snCodes={snCodes}
          loading={snLoading}
          error={snError}
          onOpenGenerate={openSnGenerateModal}
          onRefresh={loadSnCodes}
        />
      ),
    },
    {
      key: 'firmware',
      label: t('pages.gateways.firmware_mgmt'),
      children: (
        <FirmwareTab
          firmware={firmware}
          loading={fwLoading}
          error={fwError}
          onRefresh={loadFirmware}
        />
      ),
    },
    {
      key: 'tasks',
      label: t('pages.gateways.upgrade_tasks'),
      children: (
        <UpgradeTasksTab
          upgradeTasks={upgradeTasks}
          loading={taskLoading}
          error={taskError}
          onRefresh={loadUpgradeTasks}
        />
      ),
    },
  ];

  return (
    <div className="page-container">
      <Card title={t('pages.gateways.title')} extra={<Tag color="blue">{gateways.length} {t('pages.gateways.gateways_count')}</Tag>}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
      </Card>

      {/* 新增/编辑网关弹窗 */}
      <GatewayEditModal
        open={modalVisible}
        editingGateway={editingGateway}
        form={form}
        onCancel={cancelEditGateway}
        onSave={handleSaveGateway}
      />

      {/* SN码生成弹窗 */}
      <GenerateSnModal
        open={snGenerateModalVisible}
        snGenerateForm={snGenerateForm}
        onCancel={() => setSnGenerateModalVisible(false)}
        onGenerate={handleGenerateSn}
      />
    </div>
  );
};

export default GatewayPage;
