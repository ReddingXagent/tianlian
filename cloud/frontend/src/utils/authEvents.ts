/**
 * 账户变更事件 - 集中式广播/订阅
 *
 * 用于天链助手(ChatPanel)等全局组件在账户切换(登出/换号)时清空缓存状态,
 * 杜绝跨账户数据泄漏(如对话历史、页面上下文)。
 *
 * 背景: 认证态存于 localStorage(admin_token/admin_user), 无全局 store,
 * logout 走 SPA navigate 不刷新页面 → 全局挂载的 ChatPanel 不会 unmount,
 * 其内部 messages/pageContext state 会残留上一账户内容。
 * 故用 window 自定义事件(同 tab) + storage 事件(跨 tab) 解耦广播方与订阅方。
 */

export const AUTH_CHANGE_EVENT = 'tianlian:auth-change';

/** 广播账户变更(login/logout/换号)。同 tab 内立即通知所有订阅者。 */
export function broadcastAuthChange(): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new Event(AUTH_CHANGE_EVENT));
}

/**
 * 订阅账户变更。
 * - 同 tab: 监听 broadcastAuthChange 派发的自定义事件
 * - 跨 tab: 监听 storage 事件(另一个 tab 登出改写了 localStorage)
 * 返回取消订阅函数。
 */
export function subscribeAuthChange(cb: () => void): () => void {
  if (typeof window === 'undefined') return () => {};
  const handler = () => cb();
  window.addEventListener(AUTH_CHANGE_EVENT, handler);
  window.addEventListener('storage', handler);
  return () => {
    window.removeEventListener(AUTH_CHANGE_EVENT, handler);
    window.removeEventListener('storage', handler);
  };
}
