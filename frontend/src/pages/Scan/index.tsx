/**
 * 扫码报修页面 - 移动端优化
 * 
 * 功能：
 * 1. 摄像头扫码（使用 jsQR 库）
 * 2. 手动输入设备编码
 * 3. 显示设备信息
 * 4. 快速报修表单
 * 5. 报修成功展示
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Card, 
  Button, 
  Input, 
  Space, 
  Typography, 
  Result, 
  Form, 
  Select, 
  Spin,
  Tag,
  Divider,
  message,
  Row,
  Col,
  Statistic
} from 'antd';
import {
  ScanOutlined,
  CheckCircleOutlined,
  ToolOutlined,
  InfoCircleOutlined,
  ReloadOutlined
} from '@ant-design/icons';
import type { ScanResult, QuickRepairResult } from './types';
import { scanAPI } from '../../api/scan';
import QRScanner from './QRScanner';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const ScanPage: React.FC = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState<'scan' | 'device' | 'repair' | 'success'>('scan');
  const [loading, setLoading] = useState(false);
  const [deviceInfo, setDeviceInfo] = useState<ScanResult | null>(null);
  const [repairResult, setRepairResult] = useState<QuickRepairResult | null>(null);
  const [manualInput, setManualInput] = useState('');
  const [cameraError, setCameraError] = useState('');

  // ========== 扫码功能 ==========

  const handleScan = async (qrCode: string) => {
    setLoading(true);
    try {
      const result: any = await scanAPI.scanDevice(qrCode);
      setDeviceInfo(result.data || result);
      setStep('device');
      message.success('设备识别成功！');
    } catch (err: any) {
      message.error(err.response?.data?.detail || '设备识别失败，请检查二维码');
    } finally {
      setLoading(false);
    }
  };

  const handleManualScan = () => {
    if (!manualInput.trim()) {
      message.warning('请输入设备编码或序列号');
      return;
    }
    handleScan(manualInput.trim());
  };

  // ========== 快速报修 ==========

  const [repairForm] = Form.useForm();

  const handleSubmitRepair = async (values: any) => {
    if (!deviceInfo) return;
    
    setLoading(true);
    try {
      const result: any = await scanAPI.quickRepair({
        device_id: deviceInfo.device_id,
        fault_desc: values.fault_desc,
        fault_level: values.fault_level || 'warning',
        contact_name: values.contact_name,
        contact_phone: values.contact_phone,
      });
      setRepairResult(result.data || result);
      setStep('success');
      message.success('报修成功！');
    } catch (err: any) {
      message.error(err.response?.data?.detail || '报修失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  // ========== 页面渲染 ==========

  const renderScanPage = () => (
    <div style={{ padding: '16px', maxWidth: '500px', margin: '0 auto' }}>
      <Title level={3} style={{ textAlign: 'center', marginBottom: 24 }}>
        <ScanOutlined /> 扫码报修
      </Title>
      
      {/* 摄像头扫码 */}
      <Card style={{ marginBottom: 16 }}>
        <QRScanner onScan={handleScan} onError={(err) => setCameraError(err)} />
        {cameraError && <Text type="danger">{cameraError}</Text>}
      </Card>
      
      <Divider>或</Divider>
      
      {/* 手动输入 */}
      <Card>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text>手动输入设备编码/序列号：</Text>
          <Input.Search
            placeholder="输入设备编码或序列号"
            value={manualInput}
            onChange={(e) => setManualInput(e.target.value)}
            onSearch={handleManualScan}
            enterButton="识别"
            size="large"
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            示例编码：TL-DEV001, TL-DEV002
          </Text>
        </Space>
      </Card>
      
      {/* 使用说明 */}
      <Card style={{ marginTop: 16 }}>
        <Title level={5}><InfoCircleOutlined /> 使用说明</Title>
        <ul style={{ paddingLeft: 20, margin: 0 }}>
          <li>扫描设备上的二维码标签</li>
          <li>或手动输入设备编码</li>
          <li>确认设备信息后提交报修</li>
          <li>等待工程师处理</li>
        </ul>
      </Card>
    </div>
  );

  const renderDeviceInfoPage = () => (
    <div style={{ padding: '16px', maxWidth: '500px', margin: '0 auto' }}>
      <Title level={3} style={{ textAlign: 'center', marginBottom: 24 }}>
        <InfoCircleOutlined /> 设备信息
      </Title>
      
      <Spin spinning={loading}>
        {deviceInfo && (
          <>
            {/* 设备基本信息 */}
            <Card style={{ marginBottom: 16 }}>
              <Row gutter={[16, 16]}>
                <Col span={12}>
                  <Statistic 
                    title="设备名称" 
                    value={deviceInfo.device_name}
                    valueStyle={{ fontSize: 16 }}
                  />
                </Col>
                <Col span={12}>
                  <Statistic 
                    title="设备类型" 
                    value={deviceInfo.device_type}
                    valueStyle={{ fontSize: 16 }}
                  />
                </Col>
                <Col span={12}>
                  <Statistic 
                    title="设备状态" 
                    value={deviceInfo.device_status}
                    valueStyle={{ fontSize: 16 }}
                  />
                </Col>
                <Col span={12}>
                  <Statistic 
                    title="健康度" 
                    value={deviceInfo.health_score}
                    suffix="分"
                    valueStyle={{ 
                      fontSize: 16,
                      color: deviceInfo.health_score >= 80 ? '#34a853' : 
                             deviceInfo.health_score >= 60 ? '#f5a623' : '#ea4335'
                    }}
                  />
                </Col>
              </Row>
            </Card>
            
            {/* 站点信息 */}
            <Card style={{ marginBottom: 16 }}>
              <Title level={5}>所属站点</Title>
              <Paragraph>
                <Text strong>站点名称：</Text>{deviceInfo.station_name}<br />
                <Text strong>站点地址：</Text>{deviceInfo.station_address}<br />
                <Text strong>设备序列号：</Text>{deviceInfo.device_sn}<br />
                {deviceInfo.last_maintenance && (
                  <><Text strong>上次维护：</Text>{deviceInfo.last_maintenance}</>
                )}
              </Paragraph>
            </Card>
            
            {/* 操作按钮 */}
            <Space direction="vertical" style={{ width: '100%' }}>
              <Button 
                type="primary" 
                size="large"
                icon={<ToolOutlined />}
                block
                onClick={() => setStep('repair')}
              >
                立即报修
              </Button>
              <Button 
                size="large"
                icon={<ReloadOutlined />}
                block
                onClick={() => {
                  setDeviceInfo(null);
                  setStep('scan');
                }}
              >
                重新扫码
              </Button>
            </Space>
          </>
        )}
      </Spin>
    </div>
  );

  const renderRepairFormPage = () => (
    <div style={{ padding: '16px', maxWidth: '500px', margin: '0 auto' }}>
      <Title level={3} style={{ textAlign: 'center', marginBottom: 24 }}>
        <ToolOutlined /> 快速报修
      </Title>
      
      {/* 设备信息摘要 */}
      {deviceInfo && (
        <Card style={{ marginBottom: 16 }}>
          <Space>
            <Tag color="blue">{deviceInfo.device_type}</Tag>
            <Text strong>{deviceInfo.device_name}</Text>
            <Text type="secondary">{deviceInfo.station_name}</Text>
          </Space>
        </Card>
      )}
      
      {/* 报修表单 */}
      <Card>
        <Form
          form={repairForm}
          layout="vertical"
          onFinish={handleSubmitRepair}
          initialValues={{ fault_level: 'warning' }}
        >
          <Form.Item
            name="fault_desc"
            label="故障描述"
            rules={[{ required: true, message: '请描述故障情况' }]}
          >
            <TextArea 
              rows={4}
              placeholder="请详细描述故障情况，如：充电桩无法启动、显示屏异常、充电速度慢等"
            />
          </Form.Item>
          
          <Form.Item
            name="fault_level"
            label="故障级别"
          >
            <Select>
              <Select.Option value="info">提示（轻微问题）</Select.Option>
              <Select.Option value="warning">警告（影响使用）</Select.Option>
              <Select.Option value="critical">严重（紧急故障）</Select.Option>
            </Select>
          </Form.Item>
          
          <Form.Item
            name="contact_name"
            label="联系人"
          >
            <Input placeholder="联系人姓名（可选）" />
          </Form.Item>
          
          <Form.Item
            name="contact_phone"
            label="联系电话"
          >
            <Input placeholder="联系电话（可选）" />
          </Form.Item>
          
          <Form.Item>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Button 
                type="primary" 
                htmlType="submit"
                size="large"
                icon={<CheckCircleOutlined />}
                block
                loading={loading}
              >
                提交报修
              </Button>
              <Button 
                size="large"
                block
                onClick={() => setStep('device')}
              >
                返回设备信息
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );

  const renderSuccessPage = () => (
    <div style={{ padding: '16px', maxWidth: '500px', margin: '0 auto' }}>
      <Result
        status="success"
        title="报修成功！"
        subTitle={repairResult?.message}
        extra={[
          <Card key="info" style={{ marginBottom: 16 }}>
            {repairResult && (
              <Paragraph>
                <Text strong>工单号：</Text>
                <Tag color="blue">{repairResult.workorder_id}</Tag><br />
                <Text strong>设备名称：</Text>{repairResult.device_name}<br />
                <Text strong>站点：</Text>{repairResult.station_name}<br />
                <Text strong>故障描述：</Text>{repairResult.fault_desc}<br />
                <Text strong>提交时间：</Text>{repairResult.create_time}<br />
                <Text strong>当前状态：</Text>
                <Tag color="orange">等待处理</Tag>
              </Paragraph>
            )}
          </Card>,
          <Button 
            type="primary" 
            key="new"
            size="large"
            icon={<ScanOutlined />}
            block
            onClick={() => {
              setStep('scan');
              setDeviceInfo(null);
              setRepairResult(null);
              repairForm.resetFields();
            }}
          >
            继续扫码报修
          </Button>,
          <Button 
            key="home"
            size="large"
            block
            onClick={() => navigate('/workorders')}
          >
            查看工单列表
          </Button>,
        ]}
      />
    </div>
  );

  // 主渲染
  return (
    <div style={{ minHeight: '100vh', background: '#f5f5f5' }}>
      {step === 'scan' && renderScanPage()}
      {step === 'device' && renderDeviceInfoPage()}
      {step === 'repair' && renderRepairFormPage()}
      {step === 'success' && renderSuccessPage()}
    </div>
  );
};

export default ScanPage;