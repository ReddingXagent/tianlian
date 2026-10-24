/**
 * 统一错误处理工具
 * 
 * 功能：
 * - API 错误格式化
 * - 网络断开提示
 * - 超时重试
 */
import { message } from 'antd';

// 网络状态追踪
let isOnline = navigator.onLine;
let lastErrorTime = 0;

window.addEventListener('online', () => {
  isOnline = true;
  message.success('网络已恢复');
});

window.addEventListener('offline', () => {
  isOnline = false;
  message.warning('网络已断开，部分功能可能不可用');
});

/**
 * 格式化 API 错误为友好消息
 */
export function formatApiError(error: any): string {
  if (!error) return '未知错误';

  // 网络断开
  if (!isOnline) return '当前处于离线状态，请检查网络连接';

  // 超时
  if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
    return '请求超时，请稍后重试';
  }

  // 服务器错误
  if (error.response) {
    const { status, data } = error.response;
    switch (status) {
      case 400:
        return data?.detail || data?.message || '请求参数有误';
      case 401:
        return '登录已过期，请重新登录';
      case 403:
        return '权限不足，无法执行此操作';
      case 404:
        return data?.detail || '请求的资源不存在';
      case 409:
        return data?.detail || '数据冲突，请刷新后重试';
      case 429:
        return '请求过于频繁，请稍后重试';
      case 500:
        return data?.detail || '服务器内部错误，请联系管理员';
      case 502:
      case 503:
        return '服务暂不可用，请稍后重试';
      default:
        return data?.detail || data?.message || `请求失败 (${status})`;
    }
  }

  // 网络错误（无响应）
  if (error.message?.includes('Network Error')) {
    return '网络连接失败，请检查网络';
  }

  return error.message || '发生未知错误';
}

/**
 * 防抖错误提示 - 避免短时间重复弹窗刷屏
 */
let lastMessageTime = 0;
const MESSAGE_THROTTLE_MS = 3000;

export function showError(err: any, fallback?: string) {
  const now = Date.now();
  if (now - lastMessageTime < MESSAGE_THROTTLE_MS) return;
  lastMessageTime = now;

  const text = formatApiError(err);
  message.error(fallback ? `${fallback}: ${text}` : text);
}

/**
 * 创建带重试机制的异步调用
 */
export async function withRetry<T>(
  fn: () => Promise<T>,
  options?: {
    maxRetries?: number;
    retryDelayMs?: number;
    onRetry?: (attempt: number, error: any) => void;
  }
): Promise<T> {
  const maxRetries = options?.maxRetries ?? 2;
  const retryDelayMs = options?.retryDelayMs ?? 1000;
  let lastError: any;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err;
      if (attempt < maxRetries) {
        const delay = retryDelayMs * Math.pow(2, attempt); // 指数退避
        options?.onRetry?.(attempt + 1, err);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }

  throw lastError;
}

export default { formatApiError, showError, withRetry };