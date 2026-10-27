import { useState, useCallback } from 'react';
import { useRoute, RouteProp } from '@react-navigation/native';
import { useWorkOrderEnhancedStore } from '../store/workOrderEnhancedStore';
import { RootStackParamList } from '../types';

type TransferRouteProp = RouteProp<RootStackParamList, 'WorkOrderDetail'>;

/**
 * 工单转派屏数据 hook — 封装表单状态、验证、转派/催单操作。
 *
 * 职责：
 * - 从路由参数获取 orderId
 * - 表单字段管理 (assigneeId/reason)
 * - 本地验证
 * - 转派 + 催单提交到 store
 *
 * 返回纯数据 + 操作函数，不包含任何 UI。
 */
export function useWorkOrderTransfer() {
  const route = useRoute<TransferRouteProp>();
  const { orderId } = route.params;
  const { transferring, transferError, transferOrder, urgeOrder } =
    useWorkOrderEnhancedStore();

  const [assigneeId, setAssigneeId] = useState('');
  const [reason, setReason] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);

  const clearError = useCallback(() => setLocalError(null), []);

  const handleTransfer = useCallback(async (): Promise<boolean> => {
    if (!assigneeId.trim() || isNaN(Number(assigneeId))) {
      setLocalError('请输入有效的运维人员ID');
      return false;
    }
    if (!reason.trim()) {
      setLocalError('请输入转派原因');
      return false;
    }

    setLocalError(null);
    const result = await transferOrder(orderId, Number(assigneeId), reason.trim());
    return !!result;
  }, [assigneeId, reason, orderId, transferOrder]);

  const handleUrge = useCallback(async (): Promise<boolean> => {
    const result = await urgeOrder(orderId, '请尽快处理');
    return !!result;
  }, [orderId, urgeOrder]);

  return {
    orderId,
    assigneeId,
    reason,
    localError,
    transferError,
    transferring,
    setAssigneeId,
    setReason,
    clearError,
    handleTransfer,
    handleUrge,
  };
}
