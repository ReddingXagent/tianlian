/**
 * 完成报告 - 故障原因、处理方案、更换配件、照片上传
 */
import React, { useState } from 'react';
import { Modal, Form, Input, Button, Upload, message } from 'antd';
import { CheckCircleOutlined, UploadOutlined, InboxOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import api from '../../../api';

const { TextArea } = Input;
const { Dragger } = Upload;

interface CompleteReportProps {
  visible: boolean;
  orderId: string;
  onCancel: () => void;
  onSuccess: () => void;
}

const CompleteReport: React.FC<CompleteReportProps> = ({
  visible,
  orderId,
  onCancel,
  onSuccess,
}) => {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  const handleSubmit = async (values: {
    fault_reason?: string;
    solution: string;
    parts_replaced?: string;
  }) => {
    setSubmitting(true);
    try {
      // 如果有照片，先上传照片获取URL
      const photoUrls: string[] = [];
      if (fileList.length > 0) {
        for (const file of fileList) {
          if (file.originFileObj) {
            const formData = new FormData();
            formData.append('file', file.originFileObj);
            try {
              const uploadRes = await api.post('/upload', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
              });
              if (uploadRes.data?.url) {
                photoUrls.push(uploadRes.data.url);
              }
            } catch {
              message.warning(`文件 ${file.name} 上传失败`);
            }
          }
        }
      }

      await api.post(`/work-orders/${orderId}/complete`, {
        fault_reason: values.fault_reason || '',
        solution: values.solution,
        parts_replaced: values.parts_replaced || '',
        photos: photoUrls.length > 0 ? photoUrls : undefined,
      });
      message.success('已提交验收');
      form.resetFields();
      setFileList([]);
      onSuccess();
    } catch (err: unknown) {
      const error = err as any;
      message.error('提交失败: ' + (error?.response?.data?.detail || error?.message || '请重试'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleUploadChange = (info: { fileList: UploadFile[] }) => {
    setFileList(info.fileList);
  };

  return (
    <Modal
      title={
        <span>
          <CheckCircleOutlined style={{ marginRight: 8 }} />
          完成报告 - {orderId}
        </span>
      }
      open={visible}
      onCancel={() => {
        form.resetFields();
        setFileList([]);
        onCancel();
      }}
      width={600}
      footer={null}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onFinish={handleSubmit}>
        <Form.Item
          name="fault_reason"
          label="故障原因"
          tooltip="请描述故障的可能原因"
        >
          <TextArea rows={3} placeholder="请描述故障的原因（如：线路老化、设备过热、软件故障等）" />
        </Form.Item>

        <Form.Item
          name="solution"
          label="处理方案"
          rules={[{ required: true, message: '请填写处理方案' }]}
        >
          <TextArea rows={4} placeholder="请详细描述处理步骤和解决方案" />
        </Form.Item>

        <Form.Item
          name="parts_replaced"
          label="更换配件"
          tooltip="如有更换配件，请列出配件名称和数量"
        >
          <TextArea rows={2} placeholder="例如：更换接触器1个、更换保险丝2个" />
        </Form.Item>

        <Form.Item label="现场照片">
          <Dragger
            multiple
            fileList={fileList}
            onChange={handleUploadChange}
            beforeUpload={() => false}
            accept="image/*"
            listType="picture"
            maxCount={5}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">点击或拖拽照片到此区域上传</p>
            <p className="ant-upload-hint">支持 jpg、png 格式，最多5张</p>
          </Dragger>
        </Form.Item>

        <Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            loading={submitting}
            block
            icon={<CheckCircleOutlined />}
          >
            提交验收
          </Button>
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default CompleteReport;
