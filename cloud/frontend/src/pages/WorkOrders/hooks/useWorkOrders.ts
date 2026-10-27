/**
 * 工单管理页面 — 数据与交互逻辑 Hook
 *
 * 封装：工单列表拉取、WebSocket 实时刷新、统计/筛选派生数据、
 * 创建/派单/接单/开始/完成/验收/驳回/转单/催单/取消等全部操作。
 */
import { useEffect, useState, useMemo } from 'react';
import { Form, message } from 'antd';
import api from '../../../api';
import { exportObjectsCSV } from '../../../utils/csvExport';
import type { WorkOrder } from '../types';
import { typeLabels, statusLabels } from '../constants';

export function useWorkOrders() {
  const [loading, setLoading] = useState(false);
  const [orders, setOrders] = useState<WorkOrder[]>([]);
  const [createModal, setCreateModal] = useState(false);
  const [dispatchModal, setDispatchModal] = useState(false);
  const [detailVisible, setDetailVisible] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState<WorkOrder | null>(null);
  const [form] = Form.useForm();
  const [solutionForm] = Form.useForm();
  const [transferForm] = Form.useForm();
  const [rejectForm] = Form.useForm();
  // 生命周期补全：到场签到 / 申请支援 / 申请备件 / 验收评价
  const [checkInVisible, setCheckInVisible] = useState(false);
  const [supportVisible, setSupportVisible] = useState(false);
  const [sparePartsVisible, setSparePartsVisible] = useState(false);
  const [ratingVisible, setRatingVisible] = useState(false);

  // 搜索筛选
  const [searchText, setSearchText] = useState('');
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [filterLevel, setFilterLevel] = useState<string>('');

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/work-orders');
      setOrders(data.items || []);
    } catch (err: unknown) {
      const error = err as any;
      message.error('加载失败:' + (error?.response?.data?.detail || error?.message));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders();
    // WebSocket实时更新
    let ws: WebSocket | null = null;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/v1/workorders`;
    try {
      ws = new WebSocket(wsUrl);
      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === 'workorder_change' && msg.data?.event) {
            // 收到工单变更事件，刷新列表
            fetchOrders();
          }
        } catch {}
      };
      ws.onerror = () => {}; // WS不可用时静默降级
    } catch {}
    return () => { if (ws) ws.close(); };
  }, []);

  // 统计数据
  const stats = useMemo(() => ({
    total: orders.length,
    pending: orders.filter(o => o.status === 'pending').length,
    accepted: orders.filter(o => o.status === 'accepted').length,
    processing: orders.filter(o => o.status === 'processing').length,
    completed: orders.filter(o => o.status === 'completed').length,
    urgent: orders.filter(o => o.level === 'urgent' && o.status !== 'completed').length,
  }), [orders]);

  // 筛选后的数据
  const filteredOrders = useMemo(() => {
    return orders.filter(o => {
      if (filterStatus && o.status !== filterStatus) return false;
      if (filterLevel && o.level !== filterLevel) return false;
      if (searchText && !o.fault_desc.toLowerCase().includes(searchText.toLowerCase()) && !o.id.toLowerCase().includes(searchText.toLowerCase())) return false;
      return true;
    });
  }, [orders, searchText, filterStatus, filterLevel]);

  // 导出当前筛选后的工单
  const handleExportCSV = () => {
    if (filteredOrders.length === 0) {
      message.warning('没有数据可导出');
      return;
    }
    exportObjectsCSV('工单列表', filteredOrders, [
      { key: 'id', label: '工单号' },
      { key: 'fault_desc', label: '故障描述' },
      { key: 'type', label: '类型', format: (r) => typeLabels[r.type] || r.type },
      { key: 'level', label: '级别', format: (r) => r.level === 'urgent' ? '紧急' : r.level === 'high' ? '高' : r.level === 'warning' ? '一般' : r.level === 'low' ? '低' : r.level },
      { key: 'status', label: '状态', format: (r) => statusLabels[r.status] || r.status },
      { key: 'device_id', label: '设备ID' },
      { key: 'station_id', label: '站点ID' },
      { key: 'assignee_id', label: '处理人ID' },
      { key: 'create_time', label: '创建时间' },
      { key: 'accept_time', label: '接单时间' },
      { key: 'finish_time', label: '完成时间' },
    ]);
  };

  // 创建工单
  const handleCreate = async (values: { fault_desc: string; type?: string; level?: string; station_id?: number | null; device_id?: number | null }) => {
    try {
      await api.post('/work-orders', {
        fault_desc: values.fault_desc,
        type: values.type || 'repair',
        level: values.level || 'warning',
        station_id: values.station_id || null,
        device_id: values.device_id || null,
      });
      message.success('工单创建成功');
      setCreateModal(false);
      form.resetFields();
      fetchOrders();
    } catch (err: unknown) {
      const error = err as any;
      message.error('创建失败:' + (error?.response?.data?.detail || error?.message));
    }
  };

  // 智能派单
  const handleDispatch = async () => {
    if (!selectedOrder) return;
    try {
      await api.post(`/work-orders/${selectedOrder.id}/dispatch`, { auto: true });
      message.success('智能派单成功');
      setDispatchModal(false);
      setDetailVisible(false);
      fetchOrders();
    } catch (err: unknown) {
      const error = err as any;
      message.error('派单失败:' + (error?.response?.data?.detail || error?.message));
    }
  };

  // 接单
  const handleAccept = async (order: WorkOrder) => {
    try {
      await api.post(`/work-orders/${order.id}/accept`);
      message.success('已接单');
      setDetailVisible(false);
      fetchOrders();
    } catch (err: unknown) {
      message.error('接单失败');
    }
  };

  // 开始处理
  const handleStart = async (order: WorkOrder) => {
    try {
      await api.post(`/work-orders/${order.id}/start`);
      message.success('已开始处理');
      setDetailVisible(false);
      fetchOrders();
    } catch (err: unknown) {
      message.error('操作失败');
    }
  };

  // 完成工单(提交验收)
  const handleComplete = async (values: { solution: string }) => {
    if (!selectedOrder) return;
    try {
      await api.post(`/work-orders/${selectedOrder.id}/complete`, {
        solution: values.solution
      });
      message.success('已提交验收');
      setDetailVisible(false);
      setSelectedOrder(null);
      solutionForm.resetFields();
      fetchOrders();
    } catch (err: unknown) {
      message.error('操作失败');
    }
  };

  // 验收通过
  const handleVerify = async (order: WorkOrder) => {
    try {
      await api.post(`/work-orders/${order.id}/verify`);
      message.success('验收通过');
      setDetailVisible(false);
      fetchOrders();
    } catch (err: unknown) {
      message.error('操作失败');
    }
  };

  // 驳回
  const handleReject = async (values: { reason: string }) => {
    if (!selectedOrder) return;
    try {
      await api.post(`/work-orders/${selectedOrder.id}/reject`, null, {
        params: { reason: values.reason },
      });
      message.success('已驳回');
      setDetailVisible(false);
      setSelectedOrder(null);
      fetchOrders();
    } catch (err: unknown) {
      message.error('操作失败');
    }
  };

  // 转单
  const handleTransfer = async (values: { target_engineer_id: number; reason?: string }) => {
    if (!selectedOrder) return;
    try {
      await api.post(`/work-orders/${selectedOrder.id}/transfer`, {
        target_engineer_id: values.target_engineer_id,
        reason: values.reason || '工作调整',
      });
      message.success('转单成功');
      setDetailVisible(false);
      setSelectedOrder(null);
      fetchOrders();
    } catch (err: unknown) {
      message.error('操作失败');
    }
  };

  // 催单
  const handleUrge = async (order: WorkOrder) => {
    try {
      await api.post(`/work-orders/${order.id}/urge`, {
        message: '请尽快处理此工单',
      });
      message.success('已催单');
      fetchOrders();
    } catch (err: unknown) {
      message.error('催单失败');
    }
  };

  // 取消工单
  const handleCancel = async (order: WorkOrder) => {
    try {
      await api.post(`/work-orders/${order.id}/reject`, { reason: '取消工单' });
      message.success('工单已取消');
      setDetailVisible(false);
      fetchOrders();
    } catch (err: unknown) {
      message.error('操作失败');
    }
  };

  // 查看详情
  const handleViewDetail = (order: WorkOrder) => {
    setSelectedOrder(order);
    setDetailVisible(true);
  };

  return {
    loading,
    filteredOrders,
    stats,
    // 弹窗可见性与选中项
    createModal, setCreateModal,
    dispatchModal, setDispatchModal,
    detailVisible, setDetailVisible,
    selectedOrder, setSelectedOrder,
    // 生命周期补全弹窗
    checkInVisible, setCheckInVisible,
    supportVisible, setSupportVisible,
    sparePartsVisible, setSparePartsVisible,
    ratingVisible, setRatingVisible,
    // 搜索筛选
    searchText, setSearchText,
    filterStatus, setFilterStatus,
    filterLevel, setFilterLevel,
    // 表单实例
    form, solutionForm, transferForm, rejectForm,
    // 操作
    fetchOrders,
    handleExportCSV,
    handleCreate,
    handleDispatch,
    handleAccept,
    handleStart,
    handleComplete,
    handleVerify,
    handleReject,
    handleTransfer,
    handleUrge,
    handleCancel,
    handleViewDetail,
  };
}
