/**
 * 工单详情弹窗 — 基本信息 + 操作时间线 + 操作按钮 + 完成/转单/驳回表单
 */
import React from 'react';
import {
  Modal, Form, Input, Button, Descriptions, Tag, Badge, Divider,
  Space, Popconfirm, Card, Timeline,
} from 'antd';
import {
  CheckCircleOutlined, SyncOutlined, CloseCircleOutlined,
  ClockCircleOutlined, UserOutlined, ThunderboltOutlined,
  RollbackOutlined, ExclamationCircleOutlined, EnvironmentOutlined,
  TeamOutlined, ToolOutlined, StarOutlined,
} from '@ant-design/icons';
import type { FormInstance } from 'antd';
import { levelColors, statusColors, statusLabels, typeLabels } from '../constants';
import type { WorkOrder } from '../types';

const { TextArea } = Input;

interface WorkOrderDetailModalProps {
  open: boolean;
  order: WorkOrder | null;
  onCancel: () => void;
  onAccept: (o: WorkOrder) => void;
  onStart: (o: WorkOrder) => void;
  onVerify: (o: WorkOrder) => void;
  onCancelWorkOrder: (o: WorkOrder) => void;
  onUrge: (o: WorkOrder) => void;
  onCompleteSubmit: (values: { solution: string }) => void;
  onRejectSubmit: (values: { reason: string }) => void;
  onTransferSubmit: (values: { target_engineer_id: number; reason?: string }) => void;
  onAutoDispatch: () => void;
  onCheckIn: () => void;
  onSupport: () => void;
  onSpareParts: () => void;
  onRating: () => void;
  solutionForm: FormInstance;
  transferForm: FormInstance;
  rejectForm: FormInstance;
}

const WorkOrderDetailModal: React.FC<WorkOrderDetailModalProps> = ({
  open, order, onCancel,
  onAccept, onStart, onVerify, onCancelWorkOrder, onUrge,
  onCompleteSubmit, onRejectSubmit, onTransferSubmit,
  onAutoDispatch, onCheckIn, onSupport, onSpareParts, onRating,
  solutionForm, transferForm, rejectForm,
}) => (
  <Modal
    title="工单详情"
    open={open}
    onCancel={onCancel}
    width={700}
    footer={null}
  >
    {order && (
      <div>
        {/* 基本信息 */}
        <Descriptions bordered size="small" column={2} style={{ marginBottom: 16 }}>
          <Descriptions.Item label="工单号" span={2}>
            <b>{order.id}</b>
          </Descriptions.Item>
          <Descriptions.Item label="故障描述" span={2}>
            {order.fault_desc}
          </Descriptions.Item>
          <Descriptions.Item label="工单类型">
            {typeLabels[order.type] || order.type}
          </Descriptions.Item>
          <Descriptions.Item label="优先级">
            <Tag color={levelColors[order.level]}>
              {order.level === 'urgent' ? '🔴 紧急' : order.level === 'high' ? '🟠 高' : order.level === 'warning' ? '🟡 一般' : '🔵 低'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="当前状态">
            <Badge color={statusColors[order.status]} text={statusLabels[order.status]} />
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {order.create_time?.substring(0, 16)}
          </Descriptions.Item>
          <Descriptions.Item label="接单时间">
            {order.accept_time?.substring(0, 16) || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="完成时间">
            {order.finish_time?.substring(0, 16) || '-'}
          </Descriptions.Item>
          {order.station_id && (
            <Descriptions.Item label="站点ID">{order.station_id}</Descriptions.Item>
          )}
          {order.device_id && (
            <Descriptions.Item label="设备ID">{order.device_id}</Descriptions.Item>
          )}
        </Descriptions>

        {/* 操作时间线 */}
        <Card title="操作记录" size="small" style={{ marginBottom: 16 }}>
          <Timeline mode="left">
            <Timeline.Item color="blue">
              <p><ClockCircleOutlined /> 创建工单</p>
              <p style={{ color: '#999', fontSize: 12 }}>{order.create_time?.substring(0, 16)}</p>
              <p style={{ color: '#666' }}>{order.fault_desc}</p>
            </Timeline.Item>
            {order.accept_time && (
              <Timeline.Item color="green">
                <p><UserOutlined /> 接单</p>
                <p style={{ color: '#999', fontSize: 12 }}>{order.accept_time.substring(0, 16)}</p>
              </Timeline.Item>
            )}
            {order.status === 'processing' && (
              <Timeline.Item color="orange">
                <p><ThunderboltOutlined /> 开始处理</p>
              </Timeline.Item>
            )}
            {order.status === 'completed' && order.finish_time && (
              <Timeline.Item color="green">
                <p><CheckCircleOutlined /> 完成工单</p>
                <p style={{ color: '#999', fontSize: 12 }}>{order.finish_time.substring(0, 16)}</p>
                {order.solution && (
                  <p style={{ color: '#666' }}>解决方案:{order.solution}</p>
                )}
              </Timeline.Item>
            )}
            {order.status === 'cancelled' && (
              <Timeline.Item color="red">
                <p><CloseCircleOutlined /> 取消工单</p>
              </Timeline.Item>
            )}
          </Timeline>
        </Card>

        {/* 操作按钮 */}
        <Divider orientation="left" style={{ fontSize: 13 }}>操作</Divider>
        <Space wrap>
          {order.status === 'pending' && (
            <Button icon={<SyncOutlined />} onClick={onAutoDispatch}>
              智能派单
            </Button>
          )}
          {order.status === 'pending' && (
            <Popconfirm title="确认接单？" onConfirm={() => onAccept(order)}>
              <Button type="primary" ghost icon={<UserOutlined />}>接单</Button>
            </Popconfirm>
          )}
          {order.status === 'accepted' && (
            <Button type="primary" icon={<ThunderboltOutlined />} onClick={() => onStart(order)}>
              开始处理
            </Button>
          )}
          {(order.status === 'accepted' || order.status === 'processing') && (
            <>
              <Button type="primary" icon={<CheckCircleOutlined />}
                onClick={() => { solutionForm.setFieldsValue({ solution: '' }); }}>
                完成工单
              </Button>
              <Popconfirm title="确认取消此工单？" onConfirm={() => onCancelWorkOrder(order)}>
                <Button danger icon={<CloseCircleOutlined />}>取消工单</Button>
              </Popconfirm>
            </>
          )}
          {order.status === 'pending_verify' && (
            <>
              <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => onVerify(order)}>
                验收通过
              </Button>
              <Button danger icon={<CloseCircleOutlined />}
                onClick={() => { rejectForm.setFieldsValue({ reason: '' }); }}>
                驳回
              </Button>
            </>
          )}
          {(order.status === 'pending' || order.status === 'accepted' || order.status === 'processing') && (
            <Button icon={<RollbackOutlined />}
              onClick={() => { transferForm.setFieldsValue({ target_engineer_id: undefined, reason: '' }); }}>
              转单
            </Button>
          )}
          {(order.status === 'pending' || order.status === 'accepted' || order.status === 'processing') && (
            <Popconfirm title="确认催单？" onConfirm={() => onUrge(order)}>
              <Button icon={<ExclamationCircleOutlined />}>催单</Button>
            </Popconfirm>
          )}
          {(order.status === 'accepted' || order.status === 'processing') && (
            <>
              <Button icon={<EnvironmentOutlined />} onClick={onCheckIn}>到场签到</Button>
              <Button icon={<TeamOutlined />} onClick={onSupport}>申请支援</Button>
              <Button icon={<ToolOutlined />} onClick={onSpareParts}>申请备件</Button>
            </>
          )}
          {order.status === 'pending_verify' && (
            <Button type="primary" ghost icon={<StarOutlined />} onClick={onRating}>验收评价</Button>
          )}
        </Space>

        {/* 完成工单表单 */}
        {(order.status === 'accepted' || order.status === 'processing') && (
          <Form form={solutionForm} layout="vertical" onFinish={onCompleteSubmit} style={{ marginTop: 16 }}>
            <Form.Item name="solution" label="解决方案" rules={[{ required: true, message: '请填写解决方案' }]}>
              <TextArea rows={3} placeholder="请描述处理方式和解决方案" />
            </Form.Item>
          </Form>
        )}

        {/* 转单表单 */}
        {order.status !== 'completed' && order.status !== 'cancelled' && (
          <Form form={transferForm} layout="vertical" onFinish={onTransferSubmit} style={{ marginTop: 16 }}>
            <Form.Item name="target_engineer_id" label="转给工程师ID" rules={[{ required: true, message: '请输入工程师ID' }]}>
              <Input type="number" placeholder="目标工程师ID（如1001）" />
            </Form.Item>
            <Form.Item name="reason" label="转单原因">
              <TextArea rows={2} placeholder="工作调整/技能不匹配等" />
            </Form.Item>
          </Form>
        )}

        {/* 驳回表单 */}
        {order.status === 'pending_verify' && (
          <Form form={rejectForm} layout="vertical" onFinish={onRejectSubmit} style={{ marginTop: 16 }}>
            <Form.Item name="reason" label="驳回原因" rules={[{ required: true, message: '请填写驳回原因' }]}>
              <TextArea rows={3} placeholder="请说明验收不通过的原因" />
            </Form.Item>
          </Form>
        )}
      </div>
    )}
  </Modal>
);

export default WorkOrderDetailModal;
