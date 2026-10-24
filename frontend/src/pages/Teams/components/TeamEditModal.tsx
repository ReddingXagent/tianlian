/**
 * 团队 新增/编辑 弹窗（含区域选择与编码预览）
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Modal, Form, Input, Select, Row, Col, Alert } from 'antd';
import type { FormInstance } from 'antd';
import { regionOptions } from '../constants';
import type { Team, User } from '../../../types';

interface TeamEditModalProps {
  open: boolean;
  editingTeam: Team | null;
  form: FormInstance;
  previewCode: string;
  allUsers: User[];
  onRegionChange: (region: string) => void;
  onCancel: () => void;
  onSave: () => void;
}

const TeamEditModal: React.FC<TeamEditModalProps> = ({
  open, editingTeam, form, previewCode, allUsers, onRegionChange, onCancel, onSave,
}) => {
  const { t } = useTranslation();
  return (
    <Modal
      title={editingTeam ? t('pages.teams.edit') : t('pages.teams.add')}
      open={open}
      onCancel={onCancel}
      onOk={onSave}
      width={560}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="name" label={t('pages.teams.team_name')} rules={[{ required: true, message: t('pages.teams.name_required') }]}>
              <Input placeholder={t('pages.teams.name_placeholder')} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="region" label={t('pages.teams.region')}
              rules={editingTeam ? [] : [{ required: true, message: t('pages.teams.region_required') }]}
              initialValue="HN"
            >
              <Select
                placeholder={t('pages.teams.region_placeholder')}
                onChange={onRegionChange}
                disabled={!!editingTeam}
                showSearch
                optionFilterProp="label"
              >
                {regionOptions.map(opt => (
                  <Select.Option key={opt.value} value={opt.value} label={opt.label}>
                    {opt.label} ({opt.value})
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
        </Row>

        {/* 编码预览 */}
        {!editingTeam && (
          <Alert
            message={t('pages.teams.preview_code', { code: previewCode })}
            description={t('pages.teams.code_format')}
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="manager_id" label={t('pages.teams.manager')}>
              <Select placeholder={t('pages.teams.manager_placeholder')} allowClear>
                {allUsers.map((u: User) => (
                  <Select.Option key={u.id} value={u.id}>{u.real_name || u.username}</Select.Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="status" label={t('app.status')} initialValue="active">
              <Select>
                <Select.Option value="active">{t('pages.teams.status_active')}</Select.Option>
                <Select.Option value="inactive">{t('pages.teams.status_inactive')}</Select.Option>
              </Select>
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="description" label={t('app.description')}>
          <Input.TextArea rows={3} placeholder={t('pages.teams.desc_placeholder')} />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default TeamEditModal;
