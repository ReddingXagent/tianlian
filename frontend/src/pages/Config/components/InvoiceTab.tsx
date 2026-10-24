/**
 * 天链 V3 - 系统配置：发票配置 Tab
 */
import React from 'react';
import { Card, Form, Input, Select, Switch, Button, Space, Row, Col } from 'antd';
import { FileTextOutlined, SaveOutlined } from '@ant-design/icons';
import { useInvoiceConfig } from '../hooks/useInvoiceConfig';

const { Option } = Select;

const InvoiceTab: React.FC = () => {
  const { invoiceLoading, invoiceForm, handleInvoiceSave } = useInvoiceConfig();

  return (
    <Card loading={invoiceLoading} title={<Space><FileTextOutlined /> 电子发票配置</Space>}
      extra={<Button type="primary" icon={<SaveOutlined />} onClick={handleInvoiceSave}>保存</Button>}>
      <Form form={invoiceForm} layout="vertical" style={{ maxWidth: 600 }}>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="provider" label="发票服务商">
              <Select placeholder="选择服务商">
                <Option value="百望云">百望云</Option>
                <Option value="航天信息">航天信息</Option>
                <Option value="票易通">票易通</Option>
                <Option value="manual">手动开具</Option>
              </Select>
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="tax_rate" label="税率 (%)">
              <Input type="number" step="0.1" placeholder="6" />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="enabled" label="启用电子发票" valuePropName="checked">
          <Switch checkedChildren="启用" unCheckedChildren="停用" />
        </Form.Item>
        <Card type="inner" title="企业开票信息" size="small" style={{ marginBottom: 16 }}>
          <Form.Item name="company_name" label="企业名称">
            <Input placeholder="天链科技有限公司" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="tax_number" label="税号">
                <Input placeholder="91110000XXXXXXX" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="company_phone" label="企业电话">
                <Input placeholder="010-XXXXXXXX" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="bank_name" label="开户银行">
                <Input placeholder="XX银行XX支行" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="bank_account" label="银行账号">
                <Input placeholder="XXXXXXX" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="company_address" label="企业地址">
            <Input placeholder="北京市朝阳区XXX" />
          </Form.Item>
        </Card>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="reviewer" label="审核人">
              <Input placeholder="审核人姓名" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="payer" label="开票人">
              <Input placeholder="开票人姓名" />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Card>
  );
};

export default InvoiceTab;
