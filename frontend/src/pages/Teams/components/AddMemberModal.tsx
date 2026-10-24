/**
 * 添加成员弹窗
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Modal, Form, Select, Space } from 'antd';
import { CrownOutlined, ToolOutlined, UserOutlined } from '@ant-design/icons';
import type { FormInstance } from 'antd';
import type { User } from '../../../types';

interface AddMemberModalProps {
  open: boolean;
  memberForm: FormInstance;
  allUsers: User[];
  onCancel: () => void;
  onAdd: () => void;
}

const AddMemberModal: React.FC<AddMemberModalProps> = ({ open, memberForm, allUsers, onCancel, onAdd }) => {
  const { t } = useTranslation();
  return (
    <Modal
      title={t('pages.teams.add_member')}
      open={open}
      onCancel={onCancel}
      onOk={onAdd}
      width={440}
      destroyOnHidden
    >
      <Form form={memberForm} layout="vertical">
        <Form.Item name="user_id" label={t('pages.teams.select_user')} rules={[{ required: true, message: t('pages.teams.user_required') }]}>
          <Select placeholder={t('pages.teams.user_placeholder')} showSearch optionFilterProp="children">
            {allUsers.map((u: User) => (
              <Select.Option key={u.id} value={u.id}>
                {u.real_name || u.username} ({u.username})
              </Select.Option>
            ))}
          </Select>
        </Form.Item>
        <Form.Item name="role" label={t('pages.teams.role')} initialValue="technician">
          <Select>
            <Select.Option value="admin">
              <Space><CrownOutlined style={{ color: 'red' }} />管理员</Space>
            </Select.Option>
            <Select.Option value="engineer">
              <Space><ToolOutlined style={{ color: '#ff5a36' }} />工程师</Space>
            </Select.Option>
            <Select.Option value="technician">
              <Space><UserOutlined style={{ color: '#34a853' }} />技术员</Space>
            </Select.Option>
          </Select>
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default AddMemberModal;
