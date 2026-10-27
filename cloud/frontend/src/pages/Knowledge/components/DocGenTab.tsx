/**
 * 天链 V3 - 知识库：自动文档生成 Tab
 */
import React from 'react';
import {
  Card, Space, Button, Input, Select, Row, Col,
} from 'antd';
import { FileAddOutlined, DownloadOutlined } from '@ant-design/icons';
import type { DocGenState } from '../hooks/useDocGen';

const DocGenTab: React.FC<{ doc: DocGenState }> = ({ doc }) => {
  const {
    docType, setDocType, docDeviceType, setDocDeviceType,
    docFaultCode, setDocFaultCode, docTitle, setDocTitle,
    docResult, docGenLoading, handleGenerateDoc,
  } = doc;

  return (
    <Card
      title={
        <Space>
          <FileAddOutlined />
          <span>自动文档生成</span>
        </Space>
      }
    >
      <Row gutter={24}>
        <Col span={12}>
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div>
              <div style={{ marginBottom: 4, fontWeight: 500 }}>文档类型</div>
              <Select value={docType} onChange={setDocType} style={{ width: '100%' }}>
                <Select.Option value="manual">运维手册</Select.Option>
                <Select.Option value="checklist">检查清单</Select.Option>
                <Select.Option value="document">知识文档</Select.Option>
              </Select>
            </div>

            {docType === 'manual' && (
              <div>
                <div style={{ marginBottom: 4, fontWeight: 500 }}>设备类型</div>
                <Input
                  value={docDeviceType}
                  onChange={e => setDocDeviceType(e.target.value)}
                  placeholder="例如：充电桩、逆变器、变压器"
                />
              </div>
            )}

            <div>
              <div style={{ marginBottom: 4, fontWeight: 500 }}>故障码（可选）</div>
              <Input
                value={docFaultCode}
                onChange={e => setDocFaultCode(e.target.value)}
                placeholder="例如：E001、E002"
              />
            </div>

            <div>
              <div style={{ marginBottom: 4, fontWeight: 500 }}>文档标题（可选）</div>
              <Input
                value={docTitle}
                onChange={e => setDocTitle(e.target.value)}
                placeholder="自定义文档标题"
              />
            </div>

            <Button
              type="primary"
              icon={<FileAddOutlined />}
              onClick={handleGenerateDoc}
              loading={docGenLoading}
              block
            >
              生成文档
            </Button>
          </Space>
        </Col>

        <Col span={12}>
          <div style={{ marginBottom: 8, fontWeight: 500 }}>生成结果</div>
          <div
            style={{
              background: '#f6f8fa',
              border: '1px solid #e0e0e0',
              borderRadius: 8,
              padding: 16,
              minHeight: 300,
              maxHeight: 500,
              overflow: 'auto',
              fontFamily: 'monospace',
              fontSize: 13,
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
            }}
          >
            {docResult || (
              <span style={{ color: '#999' }}>在左侧填写参数后点击"生成文档"</span>
            )}
          </div>
          {docResult && (
            <Button
              style={{ marginTop: 12 }}
              icon={<DownloadOutlined />}
              onClick={() => {
                const blob = new Blob([docResult], { type: 'text/markdown' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${docTitle || '运维手册'}.md`;
                a.click();
                URL.revokeObjectURL(url);
              }}
            >
              下载 Markdown
            </Button>
          )}
        </Col>
      </Row>
    </Card>
  );
};

export default DocGenTab;
