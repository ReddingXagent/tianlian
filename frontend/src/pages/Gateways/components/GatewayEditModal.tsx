/**
 * 新增/编辑网关弹窗
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Modal, Form, Input, Select, InputNumber } from 'antd';
import type { FormInstance } from 'antd';
import type { Gateway } from '../../../types';

interface GatewayEditModalProps {
  open: boolean;
  editingGateway: Gateway | null;
  form: FormInstance;
  onCancel: () => void;
  onSave: () => void;
}

const GatewayEditModal: React.FC<GatewayEditModalProps> = ({ open, editingGateway, form, onCancel, onSave }) => {
  const { t } = useTranslation();
  return (
    <Modal
      title={editingGateway ? t('pages.gateways.edit_title', { name: editingGateway.name }) : t('pages.gateways.add')}
      open={open}
      onCancel={onCancel}
      onOk={onSave}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item name="sn" label={t('pages.gateways.sn')} rules={[{ required: true, message: t('pages.gateways.sn_required') }]}>
          <Input placeholder={t('pages.gateways.sn_placeholder')} disabled={!!editingGateway} />
        </Form.Item>
        <Form.Item name="name" label={t('pages.gateways.name')} rules={[{ required: true, message: t('pages.gateways.name_required') }]}>
          <Input placeholder={t('pages.gateways.name_placeholder')} />
        </Form.Item>
        <Form.Item name="model" label={t('pages.gateways.model')}>
          <Select placeholder={t('pages.gateways.model_placeholder')}>
            <Select.Option value="TL-GW-100">TL-GW-100</Select.Option>
            <Select.Option value="TL-GW-200">TL-GW-200</Select.Option>
            <Select.Option value="TL-GW-300">TL-GW-300</Select.Option>
            <Select.Option value="TL-GW-500">TL-GW-500</Select.Option>
          </Select>
        </Form.Item>
        <Form.Item name="station_id" label={t('pages.gateways.station_id')}>
          <InputNumber placeholder="关联站点ID" style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="ip_address" label={t('pages.gateways.ip_address')}>
          <Input placeholder={t('pages.gateways.ip_placeholder')} />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default GatewayEditModal;
