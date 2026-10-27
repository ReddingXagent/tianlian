/**
 * 天链 V3 - 系统配置：支付通道 Tab
 */
import React from 'react';
import {
  Card, Table, Button, Space, Tag, Modal, Form, Input, Select, Switch, Popconfirm,
} from 'antd';
import AutoHeightTable from '../../../components/AutoHeightTable';
import {
  CreditCardOutlined, PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined,
} from '@ant-design/icons';
import { usePaymentChannels } from '../hooks/usePaymentChannels';

const { Option } = Select;

const PaymentTab: React.FC = () => {
  const {
    payChannels, payLoading, payModalVisible, setPayModalVisible,
    editingChannel, payForm,
    fetchPayChannels, openCreateChannel, openEditChannel,
    handleChannelSubmit, handleDeleteChannel,
  } = usePaymentChannels();

  return (
    <>
      <Card
        title={<Space><CreditCardOutlined /> 支付通道管理</Space>}
        extra={
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateChannel}>新建通道</Button>
            <Button icon={<ReloadOutlined />} onClick={fetchPayChannels}>刷新</Button>
          </Space>
        }
      >
        <AutoHeightTable
          scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
          dataSource={payChannels}
          columns={[
            { title: 'ID', dataIndex: 'id', width: 60 },
            { title: '通道名称', dataIndex: 'name', width: 150 },
            {
              title: '类型', dataIndex: 'channel_type', width: 100,
              render: (t: string) => {
                const map: Record<string, string> = { im_b: 'IM-B支付', alipay: '支付宝', unionpay: '银联', bank_transfer: '对公转账' };
                return <Tag color='blue'>{map[t] || t}</Tag>;
              },
            },
            { title: 'API Key', dataIndex: 'api_key', width: 150, ellipsis: true, render: (v: string) => v ? '***' : '-' },
            {
              title: '状态', dataIndex: 'enabled', width: 80,
              render: (v: boolean) => v ? <Tag color='green'>启用</Tag> : <Tag>停用</Tag>,
            },
            { title: '排序', dataIndex: 'sort_order', width: 60 },
            {
              title: '操作', width: 150,
              render: (_: any, r: any) => (
                <Space size="small">
                  <Button size="small" icon={<EditOutlined />} onClick={() => openEditChannel(r)}>编辑</Button>
                  <Popconfirm title="确认删除该通道？" onConfirm={() => handleDeleteChannel(r.id)}>
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
          rowKey="id"
          loading={payLoading}
          pagination={false}
        />
      </Card>
      <Modal
        title={editingChannel ? '编辑支付通道' : '新建支付通道'}
        open={payModalVisible}
        onOk={handleChannelSubmit}
        onCancel={() => setPayModalVisible(false)}
        okText="保存" cancelText="取消" width={560}
      >
        <Form form={payForm} layout="vertical">
          <Form.Item name="name" label="通道名称" rules={[{ required: true, message: '请输入通道名称' }]}>
            <Input placeholder="例如：IM-B支付" />
          </Form.Item>
          <Form.Item name="channel_type" label="通道类型" rules={[{ required: true }]}>
            <Select placeholder="选择类型">
              <Option value="im_b">IM-B支付</Option>
              <Option value="alipay">支付宝</Option>
              <Option value="unionpay">银联</Option>
              <Option value="bank_transfer">对公转账</Option>
            </Select>
          </Form.Item>
          <Form.Item name="api_key" label="API Key / 商户号">
            <Input placeholder="商户号或API Key" />
          </Form.Item>
          <Form.Item name="api_secret" label="API Secret / 验签密钥">
            <Input.Password placeholder="密钥" />
          </Form.Item>
          <Form.Item name="sort_order" label="排序">
            <Input type="number" placeholder="0" />
          </Form.Item>
          <Form.Item name="enabled" label="启用状态" valuePropName="checked" initialValue={true}>
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default PaymentTab;
