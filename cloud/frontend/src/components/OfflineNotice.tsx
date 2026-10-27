import React, { useState, useEffect } from 'react';
import { Alert, Button, Space } from 'antd';
import { WifiOutlined, CloudDownloadOutlined } from '@ant-design/icons';

interface UpdateEvent extends Event {
  type: 'sw:update';
  detail?: { sw?: ServiceWorkerRegistration };
}

/**
 * 离线状态提示 & Service Worker 更新通知
 */
const OfflineNotice: React.FC = () => {
  const [offline, setOffline] = useState(!navigator.onLine);
  const [updateReady, setUpdateReady] = useState(false);
  const [waitingSW, setWaitingSW] = useState<ServiceWorker | null>(null);

  useEffect(() => {
    const handleOnline = () => setOffline(false);
    const handleOffline = () => setOffline(true);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    // Listen for SW update event from vite-plugin-pwa
    const handleSWUpdate = async (e: UpdateEvent) => {
      setUpdateReady(true);
      // The SW that's waiting is accessible via the registration
      if ('serviceWorker' in navigator) {
        try {
          const reg = await navigator.serviceWorker.getRegistration();
          if (reg?.waiting) {
            setWaitingSW(reg.waiting);
          }
        } catch {
          // 静默处理：获取 registration 失败不影响更新提示展示
        }
      }
    };

    window.addEventListener('sw:update' as any, handleSWUpdate);

    // Also check on mount for existing offline
    setOffline(!navigator.onLine);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('sw:update' as any, handleSWUpdate);
    };
  }, []);

  const handleUpdate = () => {
    if (waitingSW) {
      waitingSW.postMessage({ type: 'SKIP_WAITING' });
      setUpdateReady(false);
      window.location.reload();
    }
  };

  if (offline) {
    return (
      <Alert
        message="当前处于离线模式"
        description="您正在浏览已缓存的内容，部分实时数据可能不可用。网络恢复后自动刷新。"
        type="warning"
        showIcon
        icon={<WifiOutlined />}
        closable
        style={{ marginBottom: 16 }}
        action={
          <Button size="small" onClick={() => window.location.reload()}>
            重新连接
          </Button>
        }
      />
    );
  }

  if (updateReady) {
    return (
      <Alert
        message="新版本已就绪"
        description="系统有可用更新，点击刷新应用新版本。"
        type="info"
        showIcon
        icon={<CloudDownloadOutlined />}
        closable
        style={{ marginBottom: 16 }}
        action={
          <Space>
            <Button size="small" onClick={handleUpdate} type="primary">
              立即更新
            </Button>
            <Button size="small" onClick={() => setUpdateReady(false)}>
              稍后
            </Button>
          </Space>
        }
      />
    );
  }

  return null;
};

export default OfflineNotice;