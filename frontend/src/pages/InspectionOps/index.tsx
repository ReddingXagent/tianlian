/**
 * 天链 V3 - 巡检运维管理页面（数据库版）
 * 功能: 统计概览 + 巡检任务 + 巡检计划，全部对接后端API
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Card, Tabs, Table, Button, Modal, Form, Input, Select,
  Space, message, Tag, Row, Col, Statistic, Popconfirm, DatePicker,
} from 'antd';
import {
  EditOutlined, DeleteOutlined, PlusOutlined, ToolOutlined,
  SearchOutlined, CheckCircleOutlined,
  CalendarOutlined, ExclamationCircleOutlined, ReloadOutlined,
  PlayCircleOutlined, PauseCircleOutlined, FileProtectOutlined,
} from '@ant-design/icons';
import { inspectionAPI } from '../../api';
import { fetchAllPages } from '../../api/fetchAll';
import TemplateModal from './components/TemplateModal';
import ResultRecordModal from './components/ResultRecordModal';
import dayjs from 'dayjs';

const { TextArea } = Input;

/* ── 常量映射 ── */
const statusColors: Record<string, string> = {
  scheduled: 'cyan', in_progress: 'blue', completed: 'green',
  cancelled: 'orange', active: 'green', paused: 'orange',
};
const statusLabels: Record<string, string> = {
  scheduled: '已安排', in_progress: '进行中', completed: '已完成',
  cancelled: '已取消', active: '激活', paused: '暂停',
};
const cycleLabels: Record<string, string> = {
  daily: '每日', weekly: '每周', monthly: '每月', quarterly: '每季度', yearly: '每年',
};
const targetLabels: Record<string, string> = {
  all: '全部设备', inverter: '逆变器', battery: '储能系统', charger: '充电桩', gateway: '网关',
};

const InspectionOpsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('task');

  // ── 任务状态 ──
  const [tasks, setTasks] = useState<any[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [taskSearch, setTaskSearch] = useState('');
  const [taskFilter, setTaskFilter] = useState('');

  // ── 计划状态 ──
  const [plans, setPlans] = useState<any[]>([]);
  const [plansLoading, setPlansLoading] = useState(false);

  // ── 统计状态 ──
  const [stats, setStats] = useState<any>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  // ── 弹窗状态 ──
  const [planModalVisible, setPlanModalVisible] = useState(false);
  const [editingPlan, setEditingPlan] = useState<any>(null);
  const [planForm] = Form.useForm();
  const [taskModalVisible, setTaskModalVisible] = useState(false);
  const [editingTask, setEditingTask] = useState<any>(null);
  const [taskForm] = Form.useForm();
  // ── 巡检模板（spec 2.5）──
  const [templates, setTemplates] = useState<any[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templateModalVisible, setTemplateModalVisible] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<any>(null);
  // ── 巡检结果录入（spec 2.5）──
  const [resultVisible, setResultVisible] = useState(false);
  const [resultTask, setResultTask] = useState<{ id: number; name?: string } | null>(null);

  /* ── 加载数据 ── */
  const loadTasks = useCallback(async () => {
    setTasksLoading(true);
    try {
      const extraParams: Record<string, unknown> = {};
      if (taskFilter) extraParams.status = taskFilter;
      if (taskSearch) extraParams.keyword = taskSearch;
      const items = await fetchAllPages<any>((p) => inspectionAPI.tasks.list(p as any), extraParams);
      setTasks(items);
    } catch {
      message.error('加载任务失败');
      setTasks([]);
    }
    setTasksLoading(false);
  }, [taskFilter, taskSearch]);

  const loadPlans = useCallback(async () => {
    setPlansLoading(true);
    try {
      const items = await fetchAllPages<any>((p) => inspectionAPI.plans.list(p as any));
      setPlans(items);
    } catch {
      message.error('加载计划失败');
      setPlans([]);
    }
    setPlansLoading(false);
  }, []);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const res: any = await inspectionAPI.stats();
      setStats(res?.data || res);
    } catch {
      setStats(null);
    }
    setStatsLoading(false);
  }, []);

  // ── 巡检模板（lazy：切换到模板 Tab 时加载，避免初始请求）──
  const loadTemplates = useCallback(async () => {
    setTemplatesLoading(true);
    try {
      const items = await fetchAllPages<any>((p) => inspectionAPI.templates.list(p as any));
      setTemplates(items);
    } catch {
      message.error('加载模板失败');
      setTemplates([]);
    }
    setTemplatesLoading(false);
  }, []);

  const handleTabChange = (key: string) => {
    setActiveTab(key);
    if (key === 'template') loadTemplates();
  };

  const handleDeleteTemplate = async (id: number) => {
    try {
      await inspectionAPI.templates.delete(id);
      message.success('模板已删除');
      loadTemplates();
    } catch {
      message.error('删除失败');
    }
  };

  const loadAll = useCallback(() => {
    loadTasks();
    loadPlans();
    loadStats();
  }, [loadTasks, loadPlans, loadStats]);

  useEffect(() => { loadAll(); }, []);

  /* ── 筛选任务（客户端） ── */
  const filteredTasks = useMemo(() => {
    if (!taskSearch && !taskFilter) return tasks;
    return tasks.filter((t: any) => {
      if (taskFilter && t.status !== taskFilter) return false;
      if (taskSearch) {
        const kw = taskSearch.toLowerCase();
        if (!t.name?.toLowerCase().includes(kw) && !t.station_name?.toLowerCase().includes(kw)) return false;
      }
      return true;
    });
  }, [tasks, taskSearch, taskFilter]);

  /* ── 统计卡片数据 ── */
  const statsCards = useMemo(() => {
    const s = stats?.tasks;
    return {
      taskTotal: s?.total || 0,
      taskActive: s?.active || 0,
      taskCompleted: s?.completed || 0,
      planActive: stats?.plans?.active || 0,
    };
  }, [stats]);

  /* ── 计划CRUD ── */
  const handleSavePlan = async () => {
    try {
      const values = await planForm.validateFields();
      if (editingPlan) {
        await inspectionAPI.plans.update(editingPlan.id, values);
        message.success('计划已更新');
      } else {
        await inspectionAPI.plans.create(values);
        message.success('计划已创建');
      }
      setPlanModalVisible(false);
      planForm.resetFields();
      setEditingPlan(null);
      loadPlans();
    } catch {
      message.error(editingPlan ? '更新失败' : '创建失败');
    }
  };

  const handleDeletePlan = async (id: number) => {
    try {
      await inspectionAPI.plans.delete(id);
      message.success('计划已删除');
      loadPlans();
    } catch {
      message.error('删除失败');
    }
  };

  const handleTogglePlan = async (plan: any) => {
    const newStatus = plan.status === 'active' ? 'paused' : 'active';
    try {
      await inspectionAPI.plans.toggleStatus(plan.id, newStatus);
      message.success(newStatus === 'active' ? '计划已激活' : '计划已暂停');
      loadPlans();
    } catch {
      message.error('状态切换失败');
    }
  };

  /* ── 任务CRUD ── */
  const handleSaveTask = async () => {
    try {
      const values = await taskForm.validateFields();
      const payload = { ...values };
      if (values.scheduled_date) {
        payload.scheduled_date = dayjs(values.scheduled_date).format('YYYY-MM-DD');
      }
      if (editingTask) {
        await inspectionAPI.tasks.update(editingTask.id, payload);
        message.success('任务已更新');
      } else {
        await inspectionAPI.tasks.create(payload);
        message.success('任务已创建');
      }
      setTaskModalVisible(false);
      taskForm.resetFields();
      setEditingTask(null);
      loadTasks();
    } catch {
      message.error(editingTask ? '更新失败' : '创建失败');
    }
  };

  const handleDeleteTask = async (id: number) => {
    try {
      await inspectionAPI.tasks.delete(id);
      message.success('任务已删除');
      loadTasks();
    } catch {
      message.error('删除失败');
    }
  };

  const handleTaskStatusChange = async (task: any, newStatus: string) => {
    try {
      await inspectionAPI.tasks.update(task.id, { status: newStatus, actual_date: dayjs().format('YYYY-MM-DD') });
      message.success(`任务已${statusLabels[newStatus] || newStatus}`);
      loadTasks();
    } catch {
      message.error('状态更新失败');
    }
  };

  /* ── 打开编辑任务弹窗 ── */
  const openEditTask = (task?: any) => {
    if (task) {
      setEditingTask(task);
      taskForm.setFieldsValue({
        ...task,
        scheduled_date: task.scheduled_date ? dayjs(task.scheduled_date) : undefined,
      });
    } else {
      setEditingTask(null);
      taskForm.resetFields();
    }
    setTaskModalVisible(true);
  };

  /* ── 表格列 ── */
  const taskColumns = [
    { title: '任务名称', dataIndex: 'name', key: 'name', width: 200, ellipsis: true },
    { title: '站点', dataIndex: 'station_name', key: 'station_name', width: 140, render: (v: string) => v || '-' },
    { title: '负责人', dataIndex: 'assignee', key: 'assignee', width: 110, render: (v: string) => v || '-' },
    { title: '计划日期', dataIndex: 'scheduled_date', key: 'scheduled_date', width: 110, render: (v: string) => v || '-' },
    {
      title: '进度', key: 'progress', width: 150,
      render: (_: unknown, r: any) => {
        const pct = r.progress || 0;
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ flex: 1, height: 8, background: '#f0f0f0', borderRadius: 4, overflow: 'hidden' }}>
              <div style={{
                width: `${pct}%`, height: '100%',
                background: pct === 100 ? '#34a853' : '#ff5a36',
                transition: 'width 0.3s',
              }} />
            </div>
            <span style={{ fontSize: 12, color: '#666', minWidth: 50 }}>
              {r.completed_items}/{r.total_items} ({pct}%)
            </span>
          </div>
        );
      },
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string) => <Tag color={statusColors[v]}>{statusLabels[v] || v}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 180, fixed: 'right' as const,
      render: (_: unknown, r: any) => (
        <Space size="small">
          {r.status === 'scheduled' && (
            <Button size="small" type="primary" onClick={() => handleTaskStatusChange(r, 'in_progress')}>
              开始
            </Button>
          )}
          {r.status === 'in_progress' && (
            <Button size="small" type="primary" style={{ borderColor: '#34a853', color: '#34a853' }}
              onClick={() => handleTaskStatusChange(r, 'completed')}>
              完成
            </Button>
          )}
          {r.status === 'in_progress' && (
            <Button size="small" type="link" icon={<FileProtectOutlined />}
              onClick={() => { setResultTask({ id: r.id, name: r.name }); setResultVisible(true); }}>
              录入结果
            </Button>
          )}
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditTask(r)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDeleteTask(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const planColumns = [
    { title: '计划名称', dataIndex: 'name', key: 'name', width: 180 },
    { title: '周期', dataIndex: 'cycle', key: 'cycle', width: 80, render: (v: string) => cycleLabels[v] || v },
    { title: '巡检对象', dataIndex: 'target', key: 'target', width: 100, render: (v: string) => targetLabels[v] || v },
    { title: '下次执行', dataIndex: 'next_execute', key: 'next_execute', width: 110, render: (v: string) => v || '-' },
    { title: '上次执行', dataIndex: 'last_execute', key: 'last_execute', width: 110, render: (v: string) => v || '-' },
    { title: '任务数', dataIndex: 'task_count', key: 'task_count', width: 70 },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (v: string) => <Tag color={statusColors[v]}>{statusLabels[v] || v}</Tag>,
    },
    { title: '负责人', dataIndex: 'assignee', key: 'assignee', width: 100, render: (v: string) => v || '-' },
    {
      title: '操作', key: 'action', width: 200, fixed: 'right' as const,
      render: (_: unknown, r: any) => (
        <Space size="small">
          <Button size="small" type="link" icon={r.status === 'active' ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
            onClick={() => handleTogglePlan(r)}>
            {r.status === 'active' ? '暂停' : '激活'}
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditingPlan(r);
            planForm.setFieldsValue(r);
            setPlanModalVisible(true);
          }} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDeletePlan(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const templateColumns = [
    { title: '模板名称', dataIndex: 'name', key: 'name', width: 200, ellipsis: true },
    { title: '适用设备', dataIndex: 'target', key: 'target', width: 100, render: (v: string) => targetLabels[v] || v || '-' },
    {
      title: '巡检项数', key: 'item_count', width: 90,
      render: (_: unknown, r: any) => r.items?.length ?? r.item_count ?? 0,
    },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true, render: (v: string) => v || '-' },
    {
      title: '操作', key: 'action', width: 140, fixed: 'right' as const,
      render: (_: unknown, r: any) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />}
            onClick={() => { setEditingTemplate(r); setTemplateModalVisible(true); }} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDeleteTemplate(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="page-container">
      {/* ── 统计卡片 ── */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card size="small" loading={statsLoading}>
            <Statistic title="巡检任务" value={statsCards.taskTotal} prefix={<ToolOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" loading={statsLoading}>
            <Statistic title="执行中" value={statsCards.taskActive} valueStyle={{ color: '#ff5a36' }} prefix={<ExclamationCircleOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" loading={statsLoading}>
            <Statistic title="已完成" value={statsCards.taskCompleted} valueStyle={{ color: '#34a853' }} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" loading={statsLoading}>
            <Statistic title="执行中计划" value={statsCards.planActive} prefix={<CalendarOutlined />} />
          </Card>
        </Col>
      </Row>

      <Card>
        <Tabs activeKey={activeTab} onChange={handleTabChange}>
          {/* ── 巡检任务 Tab ── */}
          <Tabs.TabPane tab={<><ToolOutlined /> 巡检任务</>} key="task">
            <div style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <Input.Search
                placeholder="搜索任务/站点..."
                allowClear
                style={{ width: 260 }}
                value={taskSearch}
                onChange={e => setTaskSearch(e.target.value)}
                onSearch={() => loadTasks()}
              />
              <Select
                placeholder="筛选状态"
                allowClear
                style={{ width: 130 }}
                value={taskFilter || undefined}
                onChange={v => setTaskFilter(v || '')}
                options={[
                  { label: '已安排', value: 'scheduled' },
                  { label: '进行中', value: 'in_progress' },
                  { label: '已完成', value: 'completed' },
                  { label: '已取消', value: 'cancelled' },
                ]}
              />
              <Button icon={<ReloadOutlined />} onClick={loadTasks}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => openEditTask()}>新增任务</Button>
              <span style={{ color: '#999' }}>共 {tasks.length} 条</span>
            </div>
            <Table
              dataSource={filteredTasks}
              rowKey="id"
              pagination={{ pageSize: 10, showTotal: (t: number) => `共 ${t} 条` }}
              size="small"
              loading={tasksLoading}
              scroll={{ x: 1000 }}
              columns={taskColumns}
            />
          </Tabs.TabPane>

          {/* ── 巡检计划 Tab ── */}
          <Tabs.TabPane tab={<><CalendarOutlined /> 巡检计划</>} key="plan">
            <div style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
              <Button icon={<ReloadOutlined />} onClick={loadPlans}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => {
                setEditingPlan(null);
                planForm.resetFields();
                setPlanModalVisible(true);
              }}>
                新建计划
              </Button>
              <span style={{ color: '#999' }}>共 {plans.length} 条</span>
            </div>
            <Table
              dataSource={plans}
              rowKey="id"
              pagination={{ pageSize: 10, showTotal: (t: number) => `共 ${t} 条` }}
              size="small"
              loading={plansLoading}
              scroll={{ x: 1000 }}
              columns={planColumns}
            />
          </Tabs.TabPane>

          {/* ── 巡检模板 Tab（spec 2.5）── */}
          <Tabs.TabPane tab={<><FileProtectOutlined /> 巡检模板</>} key="template">
            <div style={{ marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center' }}>
              <Button icon={<ReloadOutlined />} onClick={loadTemplates}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />}
                onClick={() => { setEditingTemplate(null); setTemplateModalVisible(true); }}>
                新建模板
              </Button>
              <span style={{ color: '#999' }}>共 {templates.length} 条</span>
            </div>
            <Table
              dataSource={templates}
              rowKey="id"
              pagination={{ pageSize: 10, showTotal: (t: number) => `共 ${t} 条` }}
              size="small"
              loading={templatesLoading}
              scroll={{ x: 800 }}
              columns={templateColumns}
            />
          </Tabs.TabPane>
        </Tabs>
      </Card>

      {/* ── 计划编辑/新增弹窗 ── */}
      <Modal
        title={editingPlan ? `编辑计划 - ${editingPlan.name}` : '新建巡检计划'}
        open={planModalVisible}
        onCancel={() => { setPlanModalVisible(false); setEditingPlan(null); planForm.resetFields(); }}
        onOk={handleSavePlan}
        destroyOnHidden
      >
        <Form form={planForm} layout="vertical">
          <Form.Item name="name" label="计划名称" rules={[{ required: true, message: '请输入计划名称' }]}>
            <Input placeholder="如：每周设备巡检" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="cycle" label="执行周期" rules={[{ required: true, message: '请选择周期' }]} initialValue="weekly">
                <Select>
                  <Select.Option value="daily">每日</Select.Option>
                  <Select.Option value="weekly">每周</Select.Option>
                  <Select.Option value="monthly">每月</Select.Option>
                  <Select.Option value="quarterly">每季度</Select.Option>
                  <Select.Option value="yearly">每年</Select.Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="target" label="巡检对象" initialValue="all">
                <Select>
                  <Select.Option value="all">全部设备</Select.Option>
                  <Select.Option value="inverter">逆变器</Select.Option>
                  <Select.Option value="battery">储能系统</Select.Option>
                  <Select.Option value="charger">充电桩</Select.Option>
                  <Select.Option value="gateway">网关</Select.Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="assignee" label="负责人">
            <Input placeholder="如：运维组" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="计划描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── 任务编辑/新增弹窗 ── */}
      <Modal
        title={editingTask ? `编辑任务 - ${editingTask.name}` : '新建巡检任务'}
        open={taskModalVisible}
        onCancel={() => { setTaskModalVisible(false); setEditingTask(null); taskForm.resetFields(); }}
        onOk={handleSaveTask}
        destroyOnHidden
        width={580}
      >
        <Form form={taskForm} layout="vertical">
          <Form.Item name="name" label="任务名称" rules={[{ required: true, message: '请输入任务名称' }]}>
            <Input placeholder="如：浦东站点周巡检" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="station_name" label="站点名称">
                <Input placeholder="如：浦东充电站" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="assignee" label="负责人">
                <Input placeholder="如：张工程师" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="scheduled_date" label="计划日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="total_items" label="检查项总数" initialValue={0}>
                <Input type="number" min={0} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="description" label="任务描述">
            <TextArea rows={2} placeholder="任务描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── 巡检模板编辑弹窗（spec 2.5）── */}
      <TemplateModal
        open={templateModalVisible}
        editing={editingTemplate}
        onCancel={() => { setTemplateModalVisible(false); setEditingTemplate(null); }}
        onSuccess={() => { setTemplateModalVisible(false); setEditingTemplate(null); loadTemplates(); }}
      />

      {/* ── 巡检结果录入弹窗（spec 2.5）── */}
      <ResultRecordModal
        open={resultVisible}
        taskId={resultTask?.id ?? null}
        taskName={resultTask?.name}
        onCancel={() => setResultVisible(false)}
        onSuccess={() => setResultVisible(false)}
      />
    </div>
  );
};

export default InspectionOpsPage;