import React from 'react';
import { View, Text, StyleSheet, ActivityIndicator } from 'react-native';
import { useOffline } from '../store/OfflineContext';

/**
 * 网络状态指示器组件
 * 显示当前网络连接状态和同步状态
 */
export const NetworkStatus: React.FC = () => {
  const { isConnected, isSyncing, lastSyncTime, syncErrors } = useOffline();

  // 如果在线且不同步，不显示任何内容
  if (isConnected && !isSyncing && !syncErrors) {
    return null;
  }

  return (
    <View style={[
      styles.container,
      { 
        backgroundColor: syncErrors 
          ? '#fff1f0'  // 错误：红色背景
          : isConnected 
            ? '#e6f7ff' // 同步中：蓝色背景
            : '#fff7e6' // 离线：橙色背景
      }
    ]}>
      <View style={styles.content}>
        {isSyncing && <ActivityIndicator size="small" color="#1890ff" style={styles.spinner} />}
        
        <Text style={[
          styles.text,
          { 
            color: syncErrors 
              ? '#ff4d4f' 
              : isConnected 
                ? '#1890ff' 
                : '#fa8c16' 
          }
        ]}>
          {syncErrors 
            ? '⚠️ 同步失败，部分数据可能过期' 
            : isSyncing 
              ? '🔄 同步中...' 
              : '❌ 离线模式 - 显示缓存数据'}
        </Text>
      </View>
      
      {lastSyncTime && !syncErrors && (
        <Text style={styles.subtext}>
          上次同步：{formatTime(lastSyncTime)}
        </Text>
      )}
      
      {syncErrors && syncErrors.length > 0 && (
        <Text style={styles.errorText}>
          {syncErrors[0]}
        </Text>
      )}
    </View>
  );
};

/**
 * 格式化时间
 */
function formatTime(timestamp: number): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  
  // 1 分钟内
  if (diff < 60 * 1000) {
    return '刚刚';
  }
  
  // 1 小时内
  if (diff < 60 * 60 * 1000) {
    const minutes = Math.floor(diff / (60 * 1000));
    return `${minutes}分钟前`;
  }
  
  // 今天
  if (diff < 24 * 60 * 60 * 1000 && date.getDate() === now.getDate()) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  }
  
  // 其他日期
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const styles = StyleSheet.create({
  container: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.05)',
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  spinner: {
    marginRight: 6,
  },
  text: {
    fontSize: 12,
    fontWeight: '500',
  },
  subtext: {
    fontSize: 10,
    color: '#999',
    marginTop: 2,
  },
  errorText: {
    fontSize: 10,
    color: '#ff4d4f',
    marginTop: 2,
  },
});

export default NetworkStatus;
