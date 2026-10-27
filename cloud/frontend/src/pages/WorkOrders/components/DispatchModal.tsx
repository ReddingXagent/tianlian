/**
 * 智能派单弹窗
 */
import React from 'react';
import { Modal, Descriptions, Tag, Divider, Button } from 'antd';
import { SyncOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { levelColors } from '../constants';
import type { WorkOrder } from '../types';

interface DispatchModalProps {
  open: boolean;
  selectedOrder: WorkOrder | null;
  onDispatch: () => void;
  onCancel: () => void;
}

const DispatchModal: React.FC<DispatchModalProps> = ({ open, selectedOrder, onDispatch, onCancel }) => (
  <Modal
    title="智能派单"
    open={open}
    onCancel={onCancel}
    footer={[
      <Button key="cancel" onClick={() => onCancel()}>取消</Button>,
      <Button key="dispatch" type="primary" icon={<SyncOutlined />} onClick={onDispatch}>
        自动派单
      </Button>,
    ]}
  >
    <Descriptions bordered size="small" column={1}>
      <Descriptions.Item label="工单号">{selectedOrder?.id}</Descriptions.Item>
      <Descriptions.Item label="故障描述">{selectedOrder?.fault_desc}</Descriptions.Item>
      <Descriptions.Item label="优先级">
        <Tag color={levelColors[selectedOrder?.level as string]}>{selectedOrder?.level}</Tag>
      </Descriptions.Item>
    </Descriptions>
    <Divider />
    <p style={{ color: '#666' }}>
      <ThunderboltOutlined /> 系统将根据工程师位置、技能、负载等因素自动分配最佳工程师。
    </p>
  </Modal>
);

export default DispatchModal;
