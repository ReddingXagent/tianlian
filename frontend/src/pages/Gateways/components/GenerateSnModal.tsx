/**
 * SN 码生成弹窗（区域 + 数量 + 型号）
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Modal, Form, Select, Alert, InputNumber } from 'antd';
import type { FormInstance } from 'antd';
import { regionOptions } from '../constants';

interface GenerateSnModalProps {
  open: boolean;
  snGenerateForm: FormInstance;
  onCancel: () => void;
  onGenerate: () => void;
}

const GenerateSnModal: React.FC<GenerateSnModalProps> = ({ open, snGenerateForm, onCancel, onGenerate }) => {
  const { t } = useTranslation();
  return (
    <Modal
      title={t('pages.gateways.generate_sn')}
      open={open}
      onCancel={onCancel}
      onOk={onGenerate}
      destroyOnHidden
    >
      <Form form={snGenerateForm} layout="vertical">
        <Form.Item
          name="region"
          label={t('pages.gateways.region')}
          rules={[{ required: true, message: '请选择区域' }]}
          initialValue="HN"
        >
          <Select placeholder="选择区域生成结构化SN" showSearch optionFilterProp="label">
            {regionOptions.map(opt => (
              <Select.Option key={opt.value} value={opt.value} label={opt.label}>
                {opt.label} ({opt.value})
              </Select.Option>
            ))}
          </Select>
        </Form.Item>
        <Alert
          message={t('pages.gateways.sn_format')}
          description={t('pages.gateways.sn_example')}
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <Form.Item
          name="count"
          label={t('pages.gateways.generate_count')}
          rules={[{ required: true, message: '请输入数量' }]}
          initialValue={10}
        >
          <InputNumber
            min={1}
            max={1000}
            placeholder={t('pages.gateways.count_placeholder')}
            style={{ width: '100%' }}
          />
        </Form.Item>
        <Form.Item
          name="model"
          label={t('pages.gateways.model')}
          initialValue="TL-GW-100"
        >
          <Select placeholder={t('pages.gateways.model_placeholder')}>
            <Select.Option value="TL-GW-100">TL-GW-100</Select.Option>
            <Select.Option value="TL-GW-200">TL-GW-200</Select.Option>
            <Select.Option value="TL-GW-300">TL-GW-300</Select.Option>
            <Select.Option value="TL-GW-500">TL-GW-500</Select.Option>
          </Select>
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default GenerateSnModal;
