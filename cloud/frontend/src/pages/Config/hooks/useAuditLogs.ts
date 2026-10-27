/**
 * 天链 V3 - 系统配置：操作审计日志数据 hook
 */
import { useState, useEffect } from 'react';
import { message } from 'antd';
import { operationLogAPI } from '../../../api';
import type { LogItem } from '../types';

export function useAuditLogs() {
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logStats, setLogStats] = useState<any>({});
  const [logPagination, setLogPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [filterAction, setFilterAction] = useState('');
  const [filterModule, setFilterModule] = useState('');
  const [searchUser, setSearchUser] = useState('');

  const fetchLogs = async (page?: number) => {
    setLogsLoading(true);
    try {
      const params: any = {
        page: page || logPagination.current,
        page_size: logPagination.pageSize,
      };
      if (filterAction) params.action = filterAction;
      if (filterModule) params.module = filterModule;
      if (searchUser) params.username = searchUser;
      const res: any = await operationLogAPI.list(params);
      const data = res?.data || res;
      setLogs(data.items || []);
      setLogPagination(p => ({ ...p, total: data.total || 0, current: data.page || page || 1 }));
    } catch { message.error('获取日志失败'); }
    finally { setLogsLoading(false); }
  };

  const fetchLogStats = async () => {
    try {
      const res: any = await operationLogAPI.stats();
      const data = res?.data || res;
      setLogStats(data || {});
    } catch { /* ignore */ }
  };

  useEffect(() => {
    fetchLogs();
    fetchLogStats();
  }, []);

  return {
    logs, logsLoading, logStats, logPagination,
    filterAction, setFilterAction,
    filterModule, setFilterModule,
    searchUser, setSearchUser,
    fetchLogs, fetchLogStats,
  };
}
