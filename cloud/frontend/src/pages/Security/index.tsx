/**
 * 安全管理页面 - 增强版
 * 功能: 4 Tab(安全概览/操作日志/威胁管理/安全设置) + 筛选 + 拉黑 + Switch交互
 */
import React, { useState, useMemo, useEffect } from 'react';
import {
  Card, Row, Col, Table, Button, Tag, Space, Switch, Statistic,
  Modal, Form, Input, Select, Progress, Tabs, Timeline, message, DatePicker
} from 'antd';
import {
  SafetyOutlined, UserOutlined, GlobalOutlined, WarningOutlined,
  CheckCircleOutlined, FileTextOutlined, SettingOutlined,
  SyncOutlined, SecurityScanOutlined, BlockOutlined, PlusOutlined,
  SearchOutlined, EyeOutlined
} from '@ant-design/icons';

import { securityAPI, operationLogAPI } from '../../api';

const { TextArea } = Input;
const { RangePicker } = DatePicker;

interface SecurityLog {
  id: string;
  time: string;
  user: string;
  action: string;
  ip: string;
  result: string;
}

interface Threat {
  id: string;
  type: string;
  source: string;
  count: number;
  status: string;
  time: string;
}

interface SecuritySetting {
  key: string;
  name: string;
  desc: string;
  enabled: boolean;
}

const SecurityPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const [detailVisible, setDetailVisible] = useState(false);
  const [selectedThreat, setSelectedThreat] = useState<Threat | null>(null);
  const [blacklistVisible, setBlacklistVisible] = useState(false);
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);

  // 操作日志筛选
  const [logSearch, setLogSearch] = useState('');
  const [logFilter, setLogFilter] = useState('all');
  const [logResult, setLogResult] = useState('all');

  // 安全日志（初始空，从API加载）
  const [securityLogs, setSecurityLogs] = useState<SecurityLog[]>([]);

  // 威胁列表（初始空）
  const [threats, setThreats] = useState<Threat[]>([]);

  // 安全设置
  const [settings, setSettings] = useState<SecuritySetting[]>([
    { key: 'login_protection', name: '登录保护', desc: '连续5次失败锁定账号30分钟', enabled: true },
    { key: 'ip_whitelist', name: 'IP白名单', desc: '仅允许白名单IP访问管理后台', enabled: false },
    { key: '2fa', name: '双因素认证', desc: '登录时需要短信验证码二次验证', enabled: false },
    { key: 'operation_log', name: '操作日志', desc: '记录所有用户操作行为，保留180天', enabled: true },
    { key: 'data_encryption', name: '数据加密', desc: '敏感数据AES-256加密存储', enabled: true },
    { key: 'session_timeout', name: '会话超时', desc: '30分钟无操作自动登出', enabled: true },
    { key: 'api_rate_limit', name: 'API限流', desc: '单IP每分钟最多100次API请求', enabled: true },
    { key: 'xss_protection', name: 'XSS防护', desc: '自动过滤跨站脚本攻击', enabled: true },
    { key: 'csrf_protection', name: 'CSRF防护', desc: '跨站请求伪造保护', enabled: true },
  ]);

  // 从后端API加载安全日志
  useEffect(() => {
    fetchSecurityData();
  }, []);

  const fetchSecurityData = async () => {
    setLoading(true);
    try {
      const [logRes, statsRes] = await Promise.allSettled([
        operationLogAPI.list({ page: 1, page_size: 50 }),
        securityAPI.stats(),
      ]);

      if (logRes.status === 'fulfilled') {
        const logData = logRes.value?.data || {};
        const items = Array.isArray(logData) ? logData : (logData.items || []);
        if (items.length > 0) {
          setSecurityLogs(items.map((l: any, i: number) => ({
            id: String(l.id || i + 1),
            time: l.timestamp || l.created_at || '',
            user: l.username || l.user || '',
            action: l.action || '',
            ip: l.ip || l.ip_address || '',
            result: l.result || l.status || 'success',
          })));
        }
      }

      if (statsRes.status === 'fulfilled') {
        const stats = statsRes.value?.data || {};
        if (stats.blocked_ips) {
          const threatItems: Threat[] = Object.entries(stats.blocked_ips).map(([ip, count]: any, i: number) => ({
            id: `t-${i}`,
            type: '异常访问',
            source: ip,
            count,
            status: 'blocked',
            time: stats.last_blocked_time || new Date().toISOString(),
          }));
          setThreats(threatItems);
        }
      }
    } catch {
      // 静默处理：安全数据加载失败保留上次状态
    } finally {
      setLoading(false);
    }
  };

  // 筛选日志
  const filteredLogs = useMemo(() => {
    return securityLogs.filter(log => {
      if (logFilter !== 'all' && log.action !== logFilter) return false;
      if (logResult !== 'all' && log.result !== logResult) return false;
      if (logSearch && !log.user.includes(logSearch) && !log.action.includes(logSearch) && !log.ip.includes(logSearch)) return false;
      return true;
    });
  }, [securityLogs, logSearch, logFilter, logResult]);

  // 统计数据
  const stats = useMemo(() => ({
    successLogs: securityLogs.filter(l => l.result === 'success').length,
    failedLogs: securityLogs.filter(l => l.result === 'failed').length,
    blocked: threats.filter(t => t.status === 'blocked').length,
    warnings: threats.filter(t => t.status === 'warning').length,
  }), [securityLogs, threats]);

  const logColumns = [
    { title: '时间', dataIndex: 'time', key: 'time', width: 170 },
    { title: '用户', dataIndex: 'user', key: 'user', width: 100 },
    { title: '操作', dataIndex: 'action', key: 'action', width: 130 },
    { title: 'IP', dataIndex: 'ip', key: 'ip', width: 140 },
    {
      title: '结果', dataIndex: 'result', key: 'result', width: 80,
      render: (result: string) => (
        <Tag color={result === 'success' ? 'green' : 'red'}>
          {result === 'success' ? '成功' : '失败'}
        </Tag>
      )
    },
  ];

  const threatColumns = [
    { title: '威胁类型', dataIndex: 'type', key: 'type', width: 120 },
    { title: '来源IP', dataIndex: 'source', key: 'source', width: 140 },
    { title: '次数', dataIndex: 'count', key: 'count', width: 70 },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (status: string) => (
        <Tag color={status === 'blocked' ? 'red' : 'orange'}>
          {status === 'blocked' ? '已拦截' : '警告'}
        </Tag>
      )
    },
    { title: '时间', dataIndex: 'time', key: 'time', width: 170 },
    {
      title: '操作', key: 'action', width: 160, fixed: 'right' as const,
      render: (_: any, record: Threat) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} type="link"
            onClick={() => { setSelectedThreat(record); setDetailVisible(true); }}>详情</Button>
          {record.status !== 'blocked' && (
            <Button size="small" danger icon={<BlockOutlined />}
              onClick={() => {
                setThreats(threats.map(t => t.id === record.id ? { ...t, status: 'blocked' } : t));
                message.success(`IP ${record.source} 已拉黑`);
              }}>拉黑</Button>
          )}
        </Space>
      ),
    },
  ];

  const tabItems = [
    {
      key: 'overview',
      label: <span><SafetyOutlined /> 安全概览</span>,
      children: (
        <div>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col xs={24} sm={12} lg={6}>
              <Card size="small">
                <Statistic title="安全评分" value={85} suffix="/100" prefix={<SecurityScanOutlined />}
                  valueStyle={{ color: '#34a853' }} />
                <Progress percent={85} showInfo={false} strokeColor="#34a853" style={{ marginTop: 8 }} />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card size="small">
                <Statistic title="今日登录" value={24} prefix={<UserOutlined />} />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card size="small">
                <Statistic title="活跃威胁" value={stats.warnings}
                  prefix={<WarningOutlined />} valueStyle={{ color: stats.warnings > 0 ? '#f5a623' : '#34a853' }} />
              </Card>
            </Col>
            <Col xs={24} sm={12} lg={6}>
              <Card size="small">
                <Statistic title="已拦截" value={stats.blocked} prefix={<BlockOutlined />} valueStyle={{ color: '#ea4335' }} />
              </Card>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col xs={24} lg={12}>
              <Card title="最近威胁" size="small" extra={<Button type="link" size="small"
                onClick={() => setActiveTab('threats')}>查看全部 →</Button>}>
                <Table dataSource={threats.slice(0, 3)} columns={threatColumns.filter(c => c.key !== 'action')}
                  rowKey="id" pagination={false} size="small" />
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card title="安全建议" size="small">
                <Timeline>
                  <Timeline.Item color="orange">
                    <p><strong>建议开启双因素认证</strong></p>
                    <p style={{ color: '#a6a1a0', fontSize: 12 }}>增强账号安全性，防止密码泄露</p>
                  </Timeline.Item>
                  <Timeline.Item color="orange">
                    <p><strong>发现异常IP访问</strong></p>
                    <p style={{ color: '#a6a1a0', fontSize: 12 }}>192.168.1.200 有3次异常访问，建议关注</p>
                  </Timeline.Item>
                  <Timeline.Item color="green">
                    <p><strong>操作日志保存完整</strong></p>
                    <p style={{ color: '#a6a1a0', fontSize: 12 }}>已保留180天记录</p>
                  </Timeline.Item>
                </Timeline>
              </Card>
            </Col>
          </Row>
        </div>
      ),
    },
    {
      key: 'logs',
      label: <span><FileTextOutlined /> 操作日志</span>,
      children: (
        <Card size="small">
          <div style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Input.Search placeholder="搜索用户/IP/操作..." allowClear style={{ width: 260 }}
              prefix={<SearchOutlined />} value={logSearch} onChange={e => setLogSearch(e.target.value)} />
            <Select value={logFilter} onChange={setLogFilter} style={{ width: 130 }}
              options={[
                { label: '全部操作', value: 'all' },
                { label: '登录系统', value: '登录系统' },
                { label: '远程控制', value: '远程控制' },
                { label: '修改设备参数', value: '修改设备参数' },
                { label: '导出数据', value: '导出数据' },
              ]} />
            <Select value={logResult} onChange={setLogResult} style={{ width: 120 }}
              options={[
                { label: '全部结果', value: 'all' },
                { label: '成功', value: 'success' },
                { label: '失败', value: 'failed' },
              ]} />
            <RangePicker />
            <span style={{ lineHeight: '32px', color: '#999' }}>共 {filteredLogs.length} 条</span>
          </div>
          <Table columns={logColumns} dataSource={filteredLogs} rowKey="id"
            pagination={{ pageSize: 10, showTotal: t => `共 ${t} 条` }} size="small"
            scroll={{ x: 700 }} />
        </Card>
      ),
    },
    {
      key: 'threats',
      label: <span><WarningOutlined /> 威胁管理</span>,
      children: (
        <Card size="small"
          extra={<Button type="primary" icon={<PlusOutlined />} size="small"
            onClick={() => setBlacklistVisible(true)}>手动拉黑</Button>}>
          <Table dataSource={threats} columns={threatColumns} rowKey="id"
            pagination={{ pageSize: 10 }} size="small" scroll={{ x: 900 }} />
        </Card>
      ),
    },
    {
      key: 'settings',
      label: <span><SettingOutlined /> 安全设置</span>,
      children: (
        <Card size="small">
          <Row gutter={[16, 16]}>
            {settings.map(item => (
              <Col xs={24} sm={12} lg={8} key={item.key}>
                <Card size="small" style={{ background: item.enabled ? '#f6ffed' : '#fff7e6' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontWeight: 500, marginBottom: 4 }}>{item.name}</div>
                      <div style={{ color: '#a6a1a0', fontSize: 12 }}>{item.desc}</div>
                    </div>
                    <Switch
                      checked={item.enabled}
                      onChange={(checked) => {
                        setSettings(settings.map(s => s.key === item.key ? { ...s, enabled: checked } : s));
                        message.success(`${item.name} 已${checked ? '开启' : '关闭'}`);
                      }}
                    />
                  </div>
                </Card>
              </Col>
            ))}
          </Row>
          <div style={{ marginTop: 24, textAlign: 'right' }}>
            <Button type="primary" onClick={() => message.success('安全设置已保存')}>保存设置</Button>
          </div>
        </Card>
      ),
    },
  ];

  return (
    <div className="page-container">
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />

      {/* 威胁详情弹窗 */}
      <Modal
        title="威胁详情"
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={[
          <Button key="close" onClick={() => setDetailVisible(false)}>关闭</Button>,
          <Button key="block" type="primary" danger onClick={() => {
            if (selectedThreat) {
              setThreats(threats.map(t => t.id === selectedThreat.id ? { ...t, status: 'blocked' } : t));
              message.success(`IP ${selectedThreat.source} 已拉黑`);
            }
            setDetailVisible(false);
          }}>拉黑IP</Button>
        ]}
        width={600}
      >
        {selectedThreat && (
          <div>
            <p><strong>威胁类型：</strong>{selectedThreat.type}</p>
            <p><strong>来源IP：</strong>{selectedThreat.source}</p>
            <p><strong>攻击次数：</strong>{selectedThreat.count}</p>
            <p><strong>状态：</strong>
              <Tag color={selectedThreat.status === 'blocked' ? 'red' : 'orange'}>
                {selectedThreat.status === 'blocked' ? '已拦截' : '警告'}
              </Tag>
            </p>
            <p><strong>时间：</strong>{selectedThreat.time}</p>
          </div>
        )}
      </Modal>

      {/* IP拉黑弹窗 */}
      <Modal
        title="添加IP拉黑"
        open={blacklistVisible}
        onCancel={() => { setBlacklistVisible(false); form.resetFields(); }}
        onOk={() => {
          (async () => {
            try {
              const values = await form.validateFields();
              setThreats([...threats, {
                id: String(Date.now()),
                type: '手动拉黑',
                source: values.ip,
                count: 0,
                status: 'blocked',
                time: new Date().toISOString().substring(0, 19).replace('T', ' '),
              }]);
              message.success('IP已加入黑名单');
              setBlacklistVisible(false);
              form.resetFields();
            } catch {
              // 静默处理：表单校验失败由 antd 字段提示覆盖
            }
          })();
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="ip" label="IP地址" rules={[{ required: true, message: '请输入IP地址' }]}>
            <Input placeholder="例如：10.0.0.55" />
          </Form.Item>
          <Form.Item name="reason" label="拉黑原因">
            <TextArea rows={3} placeholder="请输入拉黑原因" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default SecurityPage;
