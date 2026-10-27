/**
 * 运维报告管理页面
 * 光储充运维报告列表、创建、编辑、删除
 */
import React, { useEffect, useState } from 'react';
import {
  Card, Table, Button, Space, Tag, Input, Select, Modal, Form,
  DatePicker, message, Popconfirm, Row, Col, Statistic, Spin
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, EyeOutlined,
  FileTextOutlined, CalendarOutlined, BarChartOutlined
} from '@ant-design/icons';
import { reportAPI } from '../../api';
import dayjs from 'dayjs';

const { Option } = Select;
const { TextArea } = Input;
const { RangePicker } = DatePicker;

interface Report {
  id: number;
  title: string;
  type: string;
  station_id?: number;
  author: string;
  status: string;
  content?: string;
  summary?: string;
  period_start?: string;
  period_end?: string;
  created_at: string;
  updated_at: string;
}

const ReportMgmtPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [reports, setReports] = useState<Report[]>([]);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [filterType, setFilterType] = useState<string | undefined>();
  const [filterStatus, setFilterStatus] = useState<string | undefined>();
  const [stats, setStats] = useState<any>({});

  // 模态框状态
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isDetailModalVisible, setIsDetailModalVisible] = useState(false);
  const [editingReport, setEditingReport] = useState<Report | null>(null);
  const [viewingReport, setViewingReport] = useState<Report | null>(null);
  const [form] = Form.useForm();

  useEffect(() => {
    fetchReports();
    fetchStats();
  }, [currentPage, pageSize, filterType, filterStatus]);

  const fetchReports = async () => {
    setLoading(true);
    try {
      const params: any = {
        page: currentPage,
        page_size: pageSize,
      };
      if (searchKeyword) params.keyword = searchKeyword;
      if (filterType) params.type = filterType;
      if (filterStatus) params.status = filterStatus;

      const res = await reportAPI.list(params);
      const data = res.data?.data || {};
      setReports(data.items || []);
      setTotal(data.total || 0);
    } catch (error) {
      message.error('获取报告列表失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const res = await reportAPI.stats();
      setStats(res.data?.data || {});
    } catch {
      // 静默处理：统计加载失败不阻塞报告列表
    }
  };

  const handleSearch = () => {
    setCurrentPage(1);
    fetchReports();
  };

  const handleCreate = () => {
    setEditingReport(null);
    form.resetFields();
    setIsModalVisible(true);
  };

  const handleEdit = (record: Report) => {
    setEditingReport(record);
    form.setFieldsValue({
      ...record,
      period: record.period_start && record.period_end
        ? [dayjs(record.period_start), dayjs(record.period_end)]
        : undefined,
    });
    setIsModalVisible(true);
  };

  const handleView = async (record: Report) => {
    try {
      const res = await reportAPI.get(record.id);
      setViewingReport(res.data?.data || record);
      setIsDetailModalVisible(true);
    } catch (error) {
      message.error('获取报告详情失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await reportAPI.delete(id);
      message.success('删除成功');
      fetchReports();
      fetchStats();
    } catch (error) {
      message.error('删除失败');
    }
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      const data: any = {
        title: values.title,
        type: values.type,
        author: values.author,
        status: values.status,
        content: values.content,
        summary: values.summary,
        station_id: values.station_id,
      };

      if (values.period && values.period.length === 2) {
        data.period_start = values.period[0].format('YYYY-MM-DD');
        data.period_end = values.period[1].format('YYYY-MM-DD');
      }

      if (editingReport) {
        await reportAPI.update(editingReport.id, data);
        message.success('更新成功');
      } else {
        await reportAPI.create(data);
        message.success('创建成功');
      }

      setIsModalVisible(false);
      fetchReports();
      fetchStats();
    } catch {
      // 静默处理：保存失败时表单校验/接口错误由 antd 字段提示覆盖
    }
  };

  const getTypeTag = (type: string) => {
    const typeMap: Record<string, { color: string; label: string }> = {
      monthly: { color: 'blue', label: '月报' },
      weekly: { color: 'green', label: '周报' },
      daily: { color: 'cyan', label: '日报' },
      inspection: { color: 'orange', label: '巡检报告' },
    };
    const config = typeMap[type] || { color: 'default', label: type };
    return <Tag color={config.color}>{config.label}</Tag>;
  };

  const getStatusTag = (status: string) => {
    const statusMap: Record<string, { color: string; label: string }> = {
      draft: { color: 'default', label: '草稿' },
      published: { color: 'success', label: '已发布' },
    };
    const config = statusMap[status] || { color: 'default', label: status };
    return <Tag color={config.color}>{config.label}</Tag>;
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 60,
    },
    {
      title: '报告标题',
      dataIndex: 'title',
      ellipsis: true,
      render: (text: string, record: Report) => (
        <a onClick={() => handleView(record)}>{text}</a>
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 100,
      render: (type: string) => getTypeTag(type),
    },
    {
      title: '作者',
      dataIndex: 'author',
      width: 120,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (status: string) => getStatusTag(status),
    },
    {
      title: '统计周期',
      width: 180,
      render: (_: any, record: Report) => (
        record.period_start && record.period_end
          ? `${record.period_start} ~ ${record.period_end}`
          : '-'
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 160,
      render: (text: string) => text ? dayjs(text).format('YYYY-MM-DD HH:mm') : '-',
    },
    {
      title: '操作',
      width: 150,
      fixed: 'right' as const,
      render: (_: any, record: Report) => (
        <Space size="small">
          <Button
            type="text"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleView(record)}
          />
          <Button
            type="text"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          />
          <Popconfirm
            title="确认删除"
            description={`确定要删除报告 "${record.title}" 吗？`}
            onConfirm={() => handleDelete(record.id)}
            okText="删除"
            cancelText="取消"
          >
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="page-container">
      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card hoverable>
            <Statistic
              title="报告总数"
              value={stats.total || 0}
              prefix={<FileTextOutlined />}
              valueStyle={{ color: '#ff5a36' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card hoverable>
            <Statistic
              title="本月新增"
              value={stats.this_month || 0}
              prefix={<CalendarOutlined />}
              valueStyle={{ color: '#34a853' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card hoverable>
            <Statistic
              title="已发布"
              value={stats.by_status?.published || 0}
              prefix={<BarChartOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card hoverable>
            <Statistic
              title="草稿"
              value={stats.by_status?.draft || 0}
              prefix={<FileTextOutlined />}
              valueStyle={{ color: '#f5a623' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 筛选和搜索 */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input.Search
            placeholder="搜索报告标题"
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
            onSearch={handleSearch}
            onPressEnter={handleSearch}
            style={{ width: 250 }}
            allowClear
          />
          <Select
            placeholder="报告类型"
            value={filterType}
            onChange={setFilterType}
            style={{ width: 120 }}
            allowClear
          >
            <Option value="monthly">月报</Option>
            <Option value="weekly">周报</Option>
            <Option value="daily">日报</Option>
            <Option value="inspection">巡检报告</Option>
          </Select>
          <Select
            placeholder="状态"
            value={filterStatus}
            onChange={setFilterStatus}
            style={{ width: 100 }}
            allowClear
          >
            <Option value="draft">草稿</Option>
            <Option value="published">已发布</Option>
          </Select>
          <Button onClick={handleSearch}>查询</Button>
          <Button onClick={() => {
            setSearchKeyword('');
            setFilterType(undefined);
            setFilterStatus(undefined);
            setCurrentPage(1);
            fetchReports();
          }}>重置</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新建报告
          </Button>
        </Space>
      </Card>

      {/* 报告列表 */}
      <Card>
        <Spin spinning={loading}>
          <Table
            columns={columns}
            dataSource={reports}
            rowKey="id"
            pagination={{
              current: currentPage,
              pageSize: pageSize,
              total: total,
              showSizeChanger: true,
              showQuickJumper: true,
              showTotal: (total) => `共 ${total} 条`,
              onChange: (page, size) => {
                setCurrentPage(page);
                if (size) setPageSize(size);
              },
            }}
            scroll={{ x: 800 }}
          />
        </Spin>
      </Card>

      {/* 创建/编辑模态框 */}
      <Modal
        title={editingReport ? '编辑报告' : '新建报告'}
        open={isModalVisible}
        onOk={handleModalOk}
        onCancel={() => setIsModalVisible(false)}
        width={700}
        okText="保存"
        cancelText="取消"
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            status: 'draft',
            author: '系统管理员',
          }}
        >
          <Row gutter={16}>
            <Col span={16}>
              <Form.Item
                name="title"
                label="报告标题"
                rules={[{ required: true, message: '请输入报告标题' }]}
              >
                <Input placeholder="请输入报告标题" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="type"
                label="报告类型"
                rules={[{ required: true, message: '请选择报告类型' }]}
              >
                <Select placeholder="选择类型">
                  <Option value="monthly">月报</Option>
                  <Option value="weekly">周报</Option>
                  <Option value="daily">日报</Option>
                  <Option value="inspection">巡检报告</Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="author"
                label="作者"
              >
                <Input placeholder="作者" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="status"
                label="状态"
                rules={[{ required: true }]}
              >
                <Select>
                  <Option value="draft">草稿</Option>
                  <Option value="published">已发布</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="station_id"
                label="关联站点ID"
              >
                <Input type="number" placeholder="站点ID" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="period"
            label="统计周期"
          >
            <RangePicker style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            name="summary"
            label="摘要"
          >
            <TextArea rows={2} placeholder="报告摘要" />
          </Form.Item>

          <Form.Item
            name="content"
            label="报告内容"
          >
            <TextArea rows={6} placeholder="详细报告内容" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 详情模态框 */}
      <Modal
        title="报告详情"
        open={isDetailModalVisible}
        onCancel={() => setIsDetailModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setIsDetailModalVisible(false)}>
            关闭
          </Button>,
        ]}
        width={800}
      >
        {viewingReport && (
          <div>
            <h2>{viewingReport.title}</h2>
            <Space style={{ marginBottom: 16 }}>
              {getTypeTag(viewingReport.type)}
              {getStatusTag(viewingReport.status)}
              <span>作者: {viewingReport.author}</span>
            </Space>

            {viewingReport.summary && (
              <Card size="small" title="摘要" style={{ marginBottom: 16 }}>
                <p>{viewingReport.summary}</p>
              </Card>
            )}

            {viewingReport.period_start && viewingReport.period_end && (
              <p style={{ color: '#888' }}>
                统计周期: {viewingReport.period_start} ~ {viewingReport.period_end}
              </p>
            )}

            <p style={{ color: '#888', fontSize: 12 }}>
              创建时间: {viewingReport.created_at ? dayjs(viewingReport.created_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
              <br />
              更新时间: {viewingReport.updated_at ? dayjs(viewingReport.updated_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
            </p>

            {viewingReport.content && (
              <Card size="small" title="内容" style={{ marginTop: 16 }}>
                <pre style={{ whiteSpace: 'pre-wrap', wordWrap: 'break-word' }}>
                  {viewingReport.content}
                </pre>
              </Card>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

export default ReportMgmtPage;
