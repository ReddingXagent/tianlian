/**
 * 平台数据管理页（卡 922b2fba, 2026-10-08 丁哥需求）
 *
 * 1. 数据导出/备份：全平台或指定租户（运营公司/运维团队），
 *    export=业务数据导出，backup=含表结构的完整备份
 * 2. 忘记密码申请处理：用户在登录页提交的申请队列，管理员标记已处理
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Radio, Select, Button, Space, Typography, message, Table, Tag,
} from 'antd';
import AutoHeightTable from '../../components/AutoHeightTable';
import {
  DownloadOutlined, DatabaseOutlined, ReloadOutlined, CheckOutlined, FileProtectOutlined,
} from '@ant-design/icons';
import { dataOpsAPI, forgotPasswordAPI, tenantAPI } from '../../api';
import { fetchAllPages } from '../../api/fetchAll';
import { downloadBlob, exportFilename } from '../../utils/download';

const { Text } = Typography;

interface TenantOption { id: number; name: string; type?: string; team_type?: string }
interface ResetRequest { id: number; account: string; status: string; created_at?: string; handled_by?: string | null }

const DataOpsPage: React.FC = () => {
  const [scope, setScope] = useState<'platform' | 'tenant'>('platform');
  const [tenantId, setTenantId] = useState<number | undefined>(undefined);
  const [mode, setMode] = useState<'export' | 'backup'>('export');
  const [tenants, setTenants] = useState<TenantOption[]>([]);
  const [downloading, setDownloading] = useState(false);

  const [requests, setRequests] = useState<ResetRequest[]>([]);
  const [requestsLoading, setRequestsLoading] = useState(false);
  const [resolvingId, setResolvingId] = useState<number | null>(null);

  const fetchTenants = useCallback(async () => {
    try {
      // 卡 604c1e16: /tenants page_size 契约 le=100, 手拼 200 必 422 → fetchAllPages 循环拉全量
      const list = await fetchAllPages<TenantOption>(tenantAPI.list);
      setTenants(list.map((t) => ({ id: t.id, name: t.name, type: t.team_type })));
    } catch {
      message.error('租户列表加载失败');
    }
  }, []);

  const fetchRequests = useCallback(async () => {
    setRequestsLoading(true);
    try {
      const res = await forgotPasswordAPI.requests();
      const list = res.data?.data?.items || res.data?.data || res.data?.items || [];
      setRequests(Array.isArray(list) ? list : []);
    } catch {
      setRequests([]);
    } finally {
      setRequestsLoading(false);
    }
  }, []);

  useEffect(() => { fetchTenants(); fetchRequests(); }, [fetchTenants, fetchRequests]);

  const handleDownload = async () => {
    if (scope === 'tenant' && !tenantId) {
      message.warning('请先选择要导出的租户');
      return;
    }
    setDownloading(true);
    try {
      const res = await dataOpsAPI.export({ scope, tenant_id: scope === 'tenant' ? tenantId : undefined, mode });
      const tenantName = tenants.find(t => t.id === tenantId)?.name || '';
      downloadBlob(
        res.data as Blob,
        exportFilename(scope === 'tenant' ? `tenant_${tenantName || tenantId}` : 'platform', mode),
      );
      message.success(mode === 'backup' ? '备份下载已开始' : '数据导出已开始');
    } catch {
      message.error('导出失败，请稍后重试');
    } finally {
      setDownloading(false);
    }
  };

  const handleResolve = async (id: number) => {
    setResolvingId(id);
    try {
      await forgotPasswordAPI.resolve(id);
      message.success('已标记处理');
      fetchRequests();
    } catch {
      message.error('操作失败');
    } finally {
      setResolvingId(null);
    }
  };

  const pendingCount = requests.filter(r => r.status === 'pending').length;

  const requestColumns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '账号', dataIndex: 'account' },
    { title: '申请时间', dataIndex: 'created_at', width: 170, render: (v: string) => v?.slice(0, 19) || '-' },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (s: string) => s === 'pending'
        ? <Tag color="orange">待处理</Tag>
        : <Tag color="green">已处理</Tag>,
    },
    {
      title: '操作', key: 'action', width: 110,
      render: (_: unknown, r: ResetRequest) => r.status === 'pending' ? (
        <Button size="small" icon={<CheckOutlined />} loading={resolvingId === r.id} onClick={() => handleResolve(r.id)}>
          标记已处理
        </Button>
      ) : <Text type="secondary">-</Text>,
    },
  ];

  return (
    <div>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card
            title={<Space><DatabaseOutlined /> 数据导出与备份</Space>}
            size="small"
          >
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <div>
                <Text type="secondary">导出范围</Text>
                <div style={{ marginTop: 4 }}>
                  <Radio.Group value={scope} onChange={e => setScope(e.target.value)}>
                    <Radio.Button value="platform">全平台</Radio.Button>
                    <Radio.Button value="tenant">指定租户</Radio.Button>
                  </Radio.Group>
                </div>
              </div>
              {scope === 'tenant' && (
                <div>
                  <Text type="secondary">选择租户（运营公司 / 运维团队 / 车队）</Text>
                  <Select
                    style={{ width: '100%', marginTop: 4 }}
                    placeholder="请选择租户"
                    showSearch
                    optionFilterProp="label"
                    value={tenantId}
                    onChange={setTenantId}
                    options={tenants.map(t => ({ value: t.id, label: `${t.name}${t.type ? `（${t.type}）` : ''}` }))}
                  />
                </div>
              )}
              <div>
                <Text type="secondary">导出方式</Text>
                <div style={{ marginTop: 4 }}>
                  <Radio.Group value={mode} onChange={e => setMode(e.target.value)}>
                    <Radio.Button value="export"><DownloadOutlined /> 业务数据导出</Radio.Button>
                    <Radio.Button value="backup"><FileProtectOutlined /> 完整备份（含表结构）</Radio.Button>
                  </Radio.Group>
                </div>
              </div>
              <Button type="primary" icon={<DownloadOutlined />} loading={downloading} onClick={handleDownload}>
                {mode === 'backup' ? '生成并下载备份' : '导出数据'}
              </Button>
              <Text type="secondary" style={{ fontSize: 12 }}>
                导出内容：站点、设备、工单、告警、订单、账户等关键业务数据；备份额外包含表结构与版本元信息。
              </Text>
            </Space>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card
            title={<Space><ReloadOutlined /> 忘记密码申请</Space>}
            size="small"
            extra={pendingCount > 0 ? <Tag color="orange">{pendingCount} 条待处理</Tag> : null}
          >
            <AutoHeightTable
              scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
              size="small"
              columns={requestColumns}
              dataSource={requests}
              rowKey="id"
              loading={requestsLoading}
              pagination={{ pageSize: 10 }}
              locale={{ emptyText: '暂无忘记密码申请' }}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              用户在登录页提交「忘记密码」申请后在此排队；处理方式：在「团队账户」列表对应用户上执行重置密码，将临时密码告知用户，再回来标记已处理。
            </Text>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default DataOpsPage;
