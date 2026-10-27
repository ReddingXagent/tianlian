// services/modules/notification.js - 通知接口 (后端暂无, 占位)

function getNotifications() {
  return Promise.resolve({ code: 200, data: { items: [], total: 0 } });
}

function markNotificationRead() {
  return Promise.resolve({ code: 200, data: null });
}

function markAllNotificationsRead() {
  return Promise.resolve({ code: 200, data: null });
}

function getUnreadNotificationCount() {
  return Promise.resolve({ code: 200, data: { count: 0 } });
}

module.exports = {
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  getUnreadNotificationCount
};
