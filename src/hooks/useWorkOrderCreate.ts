import { useState, useCallback } from 'react';
import { useWorkOrderEnhancedStore } from '../store/workOrderEnhancedStore';
import { WorkOrderType, WorkOrderPriority } from '../types';

/**
 * 工单创建屏数据 hook — 封装表单状态、验证、提交。
 *
 * 职责：
 * - 表单字段管理 (title/description/stationId/type/priority)
 * - 本地验证
 * - 提交到 store + 成功后重置
 *
 * 返回纯数据 + 操作函数，不包含任何 UI。
 */
export function useWorkOrderCreate() {
  const { creating, createError, createOrder } = useWorkOrderEnhancedStore();

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [stationId, setStationId] = useState('');
  const [type, setType] = useState<WorkOrderType>('repair');
  const [priority, setPriority] = useState<WorkOrderPriority>('normal');
  const [localError, setLocalError] = useState<string | null>(null);

  const clearError = useCallback(() => setLocalError(null), []);

  const resetForm = useCallback(() => {
    setTitle('');
    setDescription('');
    setStationId('');
    setType('repair');
    setPriority('normal');
  }, []);

  const validate = useCallback((): string | null => {
    if (!title.trim()) return '请输入工单标题';
    if (!description.trim()) return '请输入工单描述';
    if (!stationId.trim() || isNaN(Number(stationId))) return '请输入有效的站点ID';
    return null;
  }, [title, description, stationId]);

  const handleSubmit = useCallback(async () => {
    const validationError = validate();
    if (validationError) {
      setLocalError(validationError);
      return null;
    }

    setLocalError(null);
    const order = await createOrder({
      title: title.trim(),
      description: description.trim(),
      stationId: Number(stationId),
      type,
      priority,
    });

    if (order) {
      resetForm();
    }
    return order;
  }, [validate, createOrder, title, description, stationId, type, priority, resetForm]);

  return {
    title,
    description,
    stationId,
    type,
    priority,
    localError,
    createError,
    creating,
    setTitle,
    setDescription,
    setStationId,
    setType,
    setPriority,
    clearError,
    resetForm,
    handleSubmit,
  };
}
