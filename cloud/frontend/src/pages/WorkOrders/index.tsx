/**
 * 工单管理页面 - 增强版
 * 功能: 统计卡片 + 搜索筛选 + 详情弹窗 + 操作时间线 + 完整流程
 */
import React from 'react';
import { useWorkOrders } from './hooks/useWorkOrders';
import StatsCards from './components/StatsCards';
import WorkOrderListCard from './components/WorkOrderListCard';
import CreateWorkOrderModal from './components/CreateWorkOrderModal';
import DispatchModal from './components/DispatchModal';
import WorkOrderDetailModal from './components/WorkOrderDetailModal';
import CheckInModal from './components/CheckInModal';
import SupportModal from './components/SupportModal';
import SparePartsModal from './components/SparePartsModal';
import RatingModal from './components/RatingModal';

const WorkOrders: React.FC = () => {
  const {
    loading, filteredOrders, stats,
    createModal, setCreateModal,
    dispatchModal, setDispatchModal,
    detailVisible, setDetailVisible,
    selectedOrder, setSelectedOrder,
    checkInVisible, setCheckInVisible,
    supportVisible, setSupportVisible,
    sparePartsVisible, setSparePartsVisible,
    ratingVisible, setRatingVisible,
    searchText, setSearchText,
    filterStatus, setFilterStatus,
    filterLevel, setFilterLevel,
    form, solutionForm, transferForm, rejectForm,
    fetchOrders, handleExportCSV,
    handleCreate, handleDispatch,
    handleAccept, handleStart, handleComplete, handleVerify,
    handleReject, handleTransfer, handleUrge, handleCancel, handleViewDetail,
  } = useWorkOrders();

  return (
    <div className="page-container">
      {/* 统计卡片 */}
      <StatsCards stats={stats} />

      <WorkOrderListCard
        orders={filteredOrders}
        loading={loading}
        searchText={searchText}
        onSearchChange={setSearchText}
        filterStatus={filterStatus}
        onFilterStatusChange={v => setFilterStatus(v || '')}
        filterLevel={filterLevel}
        onFilterLevelChange={v => setFilterLevel(v || '')}
        onExport={handleExportCSV}
        onCreateOpen={() => setCreateModal(true)}
        onViewDetail={handleViewDetail}
        onAutoDispatch={(o) => { setSelectedOrder(o); setDispatchModal(true); }}
        onStart={handleStart}
        onComplete={(o) => { setSelectedOrder(o); solutionForm.setFieldsValue({ solution: '' }); setDetailVisible(true); }}
        onVerify={handleVerify}
        onReject={(o) => { setSelectedOrder(o); setDetailVisible(true); }}
        onTransfer={(o) => { setSelectedOrder(o); setDetailVisible(true); }}
        onUrge={handleUrge}
      />

      {/* 创建工单弹窗 */}
      <CreateWorkOrderModal
        open={createModal}
        form={form}
        onCancel={() => { setCreateModal(false); form.resetFields(); }}
        onCreate={handleCreate}
      />

      {/* 智能派单弹窗 */}
      <DispatchModal
        open={dispatchModal}
        selectedOrder={selectedOrder}
        onDispatch={handleDispatch}
        onCancel={() => { setDispatchModal(false); setSelectedOrder(null); }}
      />

      {/* 工单详情弹窗 */}
      <WorkOrderDetailModal
        open={detailVisible}
        order={selectedOrder}
        onCancel={() => { setDetailVisible(false); setSelectedOrder(null); solutionForm.resetFields(); }}
        onAccept={handleAccept}
        onStart={handleStart}
        onVerify={handleVerify}
        onCancelWorkOrder={handleCancel}
        onUrge={handleUrge}
        onCompleteSubmit={handleComplete}
        onRejectSubmit={handleReject}
        onTransferSubmit={handleTransfer}
        onAutoDispatch={() => { setDetailVisible(false); setDispatchModal(true); }}
        onCheckIn={() => setCheckInVisible(true)}
        onSupport={() => setSupportVisible(true)}
        onSpareParts={() => setSparePartsVisible(true)}
        onRating={() => setRatingVisible(true)}
        solutionForm={solutionForm}
        transferForm={transferForm}
        rejectForm={rejectForm}
      />

      {/* 生命周期补全：到场签到 / 申请支援 / 申请备件 / 验收评价 */}
      {selectedOrder && (
        <>
          <CheckInModal
            open={checkInVisible}
            orderId={selectedOrder.id}
            onCancel={() => setCheckInVisible(false)}
            onSuccess={() => { setCheckInVisible(false); fetchOrders(); }}
          />
          <SupportModal
            open={supportVisible}
            orderId={selectedOrder.id}
            onCancel={() => setSupportVisible(false)}
            onSuccess={() => { setSupportVisible(false); fetchOrders(); }}
          />
          <SparePartsModal
            open={sparePartsVisible}
            orderId={selectedOrder.id}
            onCancel={() => setSparePartsVisible(false)}
            onSuccess={() => { setSparePartsVisible(false); fetchOrders(); }}
          />
          <RatingModal
            open={ratingVisible}
            orderId={selectedOrder.id}
            onCancel={() => setRatingVisible(false)}
            onSuccess={() => { setRatingVisible(false); setDetailVisible(false); setSelectedOrder(null); fetchOrders(); }}
          />
        </>
      )}
    </div>
  );
};

export default WorkOrders;
