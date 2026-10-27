/**
 * 智能故障诊断页面 - 关键词匹配诊断
 * 
 * 功能：
 * 1. 故障描述输入
 * 2. 智能关键词识别
 * 3. 诊断结果展示
 * 4. 自动创建工单
 */
import React, { useState } from 'react';
import { Card, Form, Input, Button, Select, Tag, Space, Alert, Spin, Descriptions, Divider, List, Typography, Row, Col, message } from 'antd';
import { SearchOutlined, ToolOutlined, BulbOutlined, FileTextOutlined, CheckCircleOutlined } from '@ant-design/icons';
import smartDiagnosisApi from '../../api/smartDiagnosis';

const { TextArea } = Input;
const { Title, Text } = Typography;

const SmartDiagnosis: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [keywords, setKeywords] = useState<any[]>([]);
  const [selectedKeywords, setSelectedKeywords] = useState<string[]>([]);

  // 快速关键词标签
  const quickKeywords = [
    '通信', '离线', '故障', '异常', '电压', '电流',
    '充电', '无法启动', '充电慢', '温度', '过热',
    '逆变器', '电池', '储能', '显示',
  ];

  // 加载关键词库
  React.useEffect(() => {
    loadKeywords();
  }, []);

  const loadKeywords = async () => {
    try {
      const res = await smartDiagnosisApi.getKeywords();
      setKeywords(res.keywords || []);
    } catch {
      // 静默处理：关键词库加载失败不阻塞诊断
    }
  };

  // 智能诊断
  const handleDiagnose = async (values: any) => {
    setLoading(true);
    try {
      const res = await smartDiagnosisApi.analyze({
        device_id: values.device_id,
        fault_desc: values.fault_desc,
        fault_keywords: selectedKeywords,
      });
      setResult(res);
      message.success('诊断完成！');
    } catch {
      message.error('诊断失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  // 诊断并创建工单
  const handleDiagnoseAndRepair = async () => {
    const values = form.getFieldsValue();
    if (!values.fault_desc) {
      message.warning('请输入故障描述');
      return;
    }

    setLoading(true);
    try {
      const res = await smartDiagnosisApi.diagnoseAndRepair({
        device_id: values.device_id,
        fault_desc: values.fault_desc,
        fault_keywords: selectedKeywords,
      });
      setResult(res);
      if (res.workorder) {
        message.success(`诊断完成！已自动创建工单：${res.workorder.workorder_id}`);
      } else {
        message.success('诊断完成！');
      }
    } catch {
      message.error('诊断失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  // 快速添加关键词
  const handleQuickKeyword = (keyword: string) => {
    const currentDesc = form.getFieldValue('fault_desc') || '';
    form.setFieldsValue({
      fault_desc: currentDesc + keyword,
    });
    
    if (!selectedKeywords.includes(keyword)) {
      setSelectedKeywords([...selectedKeywords, keyword]);
    }
  };

  // 移除关键词标签
  const handleRemoveKeyword = (keyword: string) => {
    setSelectedKeywords(selectedKeywords.filter(k => k !== keyword));
  };

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <Title level={2}>🔍 智能故障诊断</Title>
      <Text type="secondary">基于关键词匹配的智能故障诊断系统</Text>

      <Divider />

      {/* 诊断表单 */}
      <Card title="故障信息输入" style={{ marginBottom: 24 }}>
        <Form form={form} layout="vertical" onFinish={handleDiagnose}>
          <Form.Item label="设备ID（可选）" name="device_id">
            <Input placeholder="输入设备ID，用于自动创建工单" type="number" />
          </Form.Item>

          <Form.Item 
            label="故障描述" 
            name="fault_desc" 
            rules={[{ required: true, message: '请输入故障描述' }]}
          >
            <TextArea 
              rows={4} 
              placeholder="描述故障现象，例如：充电桩无法启动充电、设备通信离线、逆变器温度过热等"
            />
          </Form.Item>

          {/* 快速关键词 */}
          <Form.Item label="快速关键词">
            <Space wrap>
              {quickKeywords.map(keyword => (
                <Tag 
                  key={keyword}
                  color={selectedKeywords.includes(keyword) ? 'blue' : 'default'}
                  style={{ cursor: 'pointer' }}
                  onClick={() => handleQuickKeyword(keyword)}
                >
                  {keyword}
                </Tag>
              ))}
            </Space>
          </Form.Item>

          {/* 已选关键词 */}
          {selectedKeywords.length > 0 && (
            <Form.Item label="已选关键词">
              <Space wrap>
                {selectedKeywords.map(keyword => (
                  <Tag 
                    key={keyword}
                    closable
                    color="blue"
                    onClose={() => handleRemoveKeyword(keyword)}
                  >
                    {keyword}
                  </Tag>
                ))}
              </Space>
            </Form.Item>
          )}

          <Form.Item>
            <Space>
              <Button 
                type="primary" 
                icon={<SearchOutlined />} 
                htmlType="submit"
                loading={loading}
              >
                智能诊断
              </Button>
              <Button 
                type="default" 
                icon={<ToolOutlined />} 
                onClick={handleDiagnoseAndRepair}
                loading={loading}
              >
                诊断并创建工单
              </Button>
              <Button onClick={() => { form.resetFields(); setResult(null); setSelectedKeywords([]); }}>
                清空
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      {/* 诊断结果 */}
      {loading && (
        <Card>
          <Spin tip="正在诊断故障...">
            <div style={{ height: 200 }} />
          </Spin>
        </Card>
      )}

      {result && !loading && (
        <Card title="诊断结果" extra={<Tag color={result.fault_level === 'critical' ? 'red' : result.fault_level === 'warning' ? 'orange' : 'green'}>{result.fault_level}</Tag>}>
          {/* 诊断概要 */}
          <Alert 
            message={result.message} 
            type="success" 
            showIcon 
            style={{ marginBottom: 16 }}
          />

          {/* 置信度 */}
          <Descriptions bordered column={2} style={{ marginBottom: 24 }}>
            <Descriptions.Item label="故障类型">{result.fault_type}</Descriptions.Item>
            <Descriptions.Item label="置信度">{Math.round(result.confidence * 100)}%</Descriptions.Item>
            <Descriptions.Item label="匹配关键词">
              {result.matched_keywords?.map((k: string) => (
                <Tag key={k} color="blue">{k}</Tag>
              ))}
            </Descriptions.Item>
            <Descriptions.Item label="建议创建工单">
              {result.auto_create_workorder ? <CheckCircleOutlined style={{ color: 'green' }} /> : '否'}
            </Descriptions.Item>
          </Descriptions>

          {/* 工单信息 */}
          {result.workorder && (
            <Alert 
              message={`已自动创建工单：${result.workorder.workorder_id}`}
              description={result.workorder.message}
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
          )}

          {/* 可能原因 */}
          <Card title={<><BulbOutlined /> 可能原因</>} type="inner" style={{ marginBottom: 16 }}>
            <List
              dataSource={result.possible_causes}
              renderItem={(item: string) => (
                <List.Item>
                  <Text>{item}</Text>
                </List.Item>
              )}
            />
          </Card>

          {/* 推荐处理步骤 */}
          <Card title={<><ToolOutlined /> 推荐处理步骤</>} type="inner" style={{ marginBottom: 16 }}>
            <List
              dataSource={result.recommended_actions}
              renderItem={(item: string, index: number) => (
                <List.Item>
                  <Text mark>{index + 1}.</Text> <Text>{item}</Text>
                </List.Item>
              )}
            />
          </Card>

          {/* 相关知识库文章 */}
          {result.related_articles && result.related_articles.length > 0 && (
            <Card title={<><FileTextOutlined /> 相关知识库文章</>} type="inner">
              <List
                dataSource={result.related_articles}
                renderItem={(article: any) => (
                  <List.Item>
                    <List.Item.Meta
                      title={article.title}
                      description={article.summary}
                    />
                    <Tag>{article.category}</Tag>
                  </List.Item>
                )}
              />
            </Card>
          )}
        </Card>
      )}

      {/* 关键词库 */}
      <Card title="故障关键词库" style={{ marginTop: 24 }}>
        <Row gutter={[16, 16]}>
          {keywords.map((item: any) => (
            <Col xs={24} sm={12} md={8} lg={6} key={item.keyword}>
              <Card size="small">
                <Space direction="vertical" size="small">
                  <Tag color={item.level === 'critical' ? 'red' : item.level === 'warning' ? 'orange' : 'green'}>
                    {item.keyword}
                  </Tag>
                  <Text type="secondary">{item.type}</Text>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>
    </div>
  );
};

export default SmartDiagnosis;