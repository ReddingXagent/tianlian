import React, { useState, useEffect } from 'react';
import {
  Form,
  Input,
  InputNumber,
  ColorPicker,
  Select,
  Switch,
  Slider,
  Card,
  Row,
  Col,
  Button,
  Space,
  Divider,
  Tabs,
  message,
  Typography,
  List,
  Tag
} from 'antd';
import {
  SettingOutlined,
  SaveOutlined,
  ReloadOutlined,
  EyeOutlined,
  HighlightOutlined,
  EnvironmentOutlined,
  CameraOutlined,
  BulbOutlined
} from '@ant-design/icons';

const { Title } = Typography;

interface SceneSettingsProps {
  scene: any;
  devices: any[];
  onUpdateScene: (config: any) => Promise<void>;
  onUpdateDevice: (deviceId: number, config: any) => Promise<void>;
  onClose: () => void;
}

const SceneSettings: React.FC<SceneSettingsProps> = ({
  scene,
  devices,
  onUpdateScene,
  onUpdateDevice,
  onClose
}) => {
  const [form] = Form.useForm();
  const [deviceForm] = Form.useForm();
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedTab, setSelectedTab] = useState('general');

  useEffect(() => {
    if (scene) {
      form.setFieldsValue({
        name: scene.name || '默认场景',
        description: scene.description || '',
        backgroundColor: scene.config?.backgroundColor || '#1a1a1a',
        ambientLight: scene.config?.ambientLight || 0.5,
        directionalLight: scene.config?.directionalLight || 1,
        showGrid: scene.config?.showGrid ?? true,
        showAxes: scene.config?.showAxes ?? true,
        showShadows: scene.config?.showShadows ?? true,
        showLabels: scene.config?.showLabels ?? true,
        cameraDistance: scene.config?.cameraDistance || 20,
        cameraFOV: scene.config?.cameraFOV || 75,
        floorColor: scene.config?.floorColor || '#333333',
        floorOpacity: scene.config?.floorOpacity || 1,
        floorRoughness: scene.config?.floorRoughness || 0.8,
        floorMetalness: scene.config?.floorMetalness || 0.2,
        gridSize: scene.config?.gridSize || 50,
        gridDivisions: scene.config?.gridDivisions || 50,
        fogDensity: scene.config?.fogDensity || 0.05,
        fogColor: scene.config?.fogColor || '#1a1a1a'
      });
    }
  }, [scene, form]);

  const selectedDevice = selectedDeviceId
    ? devices.find(d => d.device.id === selectedDeviceId)?.device
    : null;

  const handleSaveScene = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      const config = {
        name: values.name,
        description: values.description,
        config: {
          backgroundColor: values.backgroundColor,
          ambientLight: values.ambientLight,
          directionalLight: values.directionalLight,
          showGrid: values.showGrid,
          showAxes: values.showAxes,
          showShadows: values.showShadows,
          showLabels: values.showLabels,
          cameraDistance: values.cameraDistance,
          cameraFOV: values.cameraFOV,
          floorColor: values.floorColor,
          floorOpacity: values.floorOpacity,
          floorRoughness: values.floorRoughness,
          floorMetalness: values.floorMetalness,
          gridSize: values.gridSize,
          gridDivisions: values.gridDivisions,
          fogDensity: values.fogDensity,
          fogColor: values.fogColor
        }
      };

      await onUpdateScene(config);
      message.success('场景配置已保存');
      setLoading(false);
    } catch (error) {
      message.error('保存失败');
      setLoading(false);
    }
  };

  const handleSaveDevice = async () => {
    if (!selectedDeviceId) {
      message.warning('请选择一个设备');
      return;
    }

    try {
      const values = await deviceForm.validateFields();
      setLoading(true);

      const config = {
        ...selectedDevice,
        ...values,
        config: {
          ...selectedDevice?.config,
          ...values.config
        }
      };

      await onUpdateDevice(selectedDeviceId, config);
      message.success('设备配置已保存');
      setLoading(false);
    } catch (error) {
      message.error('保存失败');
      setLoading(false);
    }
  };

  const handleReset = () => {
    if (selectedTab === 'general') {
      form.resetFields();
      if (scene) {
        form.setFieldsValue({
          name: scene.name,
          description: scene.description,
          ...(scene.config || {})
        });
      }
    } else {
      deviceForm.resetFields();
      if (selectedDevice) {
        deviceForm.setFieldsValue({
          name: selectedDevice.name,
          location: selectedDevice.location,
          ...(selectedDevice.config || {})
        });
      }
    }
    message.info('配置已重置');
  };

  // ==================== 通用设置面板 ====================
  const generalTab = (
    <Form form={form} layout="vertical" initialValues={scene?.config || {}}>
      <Row gutter={16}>
        <Col span={12}>
          <Form.Item name="name" label="场景名称" rules={[{ required: true, message: '请输入场景名称' }]}>
            <Input placeholder="请输入场景名称" />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="backgroundColor" label="背景颜色">
            <ColorPicker showText format="hex" allowClear />
          </Form.Item>
        </Col>
      </Row>

      <Form.Item name="description" label="场景描述">
        <Input.TextArea placeholder="请输入场景描述" rows={2} />
      </Form.Item>

      <Divider orientation="left" plain><BulbOutlined /> 灯光设置</Divider>

      <Row gutter={16}>
        <Col span={12}>
          <Form.Item name="ambientLight" label="环境光强度">
            <Slider min={0} max={1} step={0.1} marks={{ 0: '弱', 0.5: '中', 1: '强' }} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="directionalLight" label="方向光强度">
            <Slider min={0} max={2} step={0.1} marks={{ 0: '关', 1: '标准', 2: '强' }} />
          </Form.Item>
        </Col>
      </Row>

      <Divider orientation="left" plain><EyeOutlined /> 显示设置</Divider>

      <Row gutter={16}>
        <Col span={6}>
          <Form.Item name="showGrid" label="显示网格" valuePropName="checked"><Switch /></Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item name="showAxes" label="显示坐标轴" valuePropName="checked"><Switch /></Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item name="showShadows" label="显示阴影" valuePropName="checked"><Switch /></Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item name="showLabels" label="显示标签" valuePropName="checked"><Switch /></Form.Item>
        </Col>
      </Row>

      <Divider orientation="left" plain><CameraOutlined /> 相机设置</Divider>

      <Row gutter={16}>
        <Col span={12}>
          <Form.Item name="cameraDistance" label="相机距离">
            <InputNumber min={1} max={100} style={{ width: '100%' }} addonAfter="米" />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="cameraFOV" label="视野角度">
            <InputNumber min={30} max={120} style={{ width: '100%' }} addonAfter="度" />
          </Form.Item>
        </Col>
      </Row>

      <Divider orientation="left" plain><EnvironmentOutlined /> 地面设置</Divider>

      <Row gutter={16}>
        <Col span={6}>
          <Form.Item name="floorColor" label="地面颜色"><ColorPicker showText format="hex" /></Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item name="floorOpacity" label="透明度">
            <Slider min={0} max={1} step={0.1} marks={{ 0: '透明', 0.5: '半透明', 1: '不透明' }} />
          </Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item name="floorRoughness" label="粗糙度">
            <Slider min={0} max={1} step={0.1} marks={{ 0: '光滑', 0.5: '中等', 1: '粗糙' }} />
          </Form.Item>
        </Col>
        <Col span={6}>
          <Form.Item name="floorMetalness" label="金属度">
            <Slider min={0} max={1} step={0.1} marks={{ 0: '非金属', 0.5: '半金属', 1: '金属' }} />
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Form.Item name="gridSize" label="网格大小">
            <InputNumber min={10} max={100} style={{ width: '100%' }} addonAfter="米" />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="gridDivisions" label="网格分割数">
            <InputNumber min={10} max={100} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>

      <Divider orientation="left" plain><HighlightOutlined /> 雾气设置</Divider>

      <Row gutter={16}>
        <Col span={12}>
          <Form.Item name="fogDensity" label="雾气密度">
            <Slider min={0} max={0.1} step={0.01} marks={{ 0: '无雾', 0.05: '标准', 0.1: '浓雾' }} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="fogColor" label="雾气颜色"><ColorPicker showText format="hex" /></Form.Item>
        </Col>
      </Row>
    </Form>
  );

  // ==================== 设备设置面板 ====================
  const devicesTab = (
    <div style={{ display: 'flex', height: '500px' }}>
      <div style={{ width: '200px', borderRight: '1px solid #f0f0f0', paddingRight: '16px' }}>
        <div style={{ marginBottom: '16px', fontWeight: 'bold' }}>设备列表</div>
        <List
          dataSource={devices}
          renderItem={(item) => (
            <List.Item
              style={{
                padding: '8px 12px',
                cursor: 'pointer',
                backgroundColor: selectedDeviceId === item.device.id ? '#fef0ed' : 'transparent',
                border: selectedDeviceId === item.device.id ? '1px solid #ff5a36' : '1px solid transparent',
                borderRadius: '4px',
                marginBottom: '4px'
              }}
              onClick={() => {
                setSelectedDeviceId(item.device.id);
                deviceForm.setFieldsValue({
                  name: item.device.name,
                  location: item.device.location,
                  ...(item.device.config || {})
                });
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: '500' }}>{item.device.name}</div>
                  <div style={{ fontSize: '12px', color: '#666' }}>{item.device.type}</div>
                </div>
                <Tag color={item.device.status === 'online' ? 'green' : item.device.status === 'fault' ? 'red' : 'default'}>
                  {item.device.status === 'online' ? '在线' : '故障'}
                </Tag>
              </div>
            </List.Item>
          )}
        />
      </div>

      <div style={{ flex: 1, paddingLeft: '16px', overflow: 'auto' }}>
        {selectedDevice ? (
          <Form form={deviceForm} layout="vertical">
            <Title level={5}>{selectedDevice.name} 配置</Title>

            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="name" label="设备名称" rules={[{ required: true, message: '请输入设备名称' }]}>
                  <Input placeholder="请输入设备名称" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="location" label="设备位置">
                  <Input placeholder="请输入设备位置" />
                </Form.Item>
              </Col>
            </Row>

            <Form.Item name="model" label="设备型号">
              <Input placeholder="请输入设备型号" />
            </Form.Item>

            <Divider orientation="left" plain>3D模型设置</Divider>

            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name={['config', 'modelScale']} label="模型缩放" initialValue={1}>
                  <InputNumber min={0.1} max={5} step={0.1} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name={['config', 'modelColor']} label="模型颜色" initialValue="#ff5a36">
                  <ColorPicker showText format="hex" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name={['config', 'modelOpacity']} label="透明度" initialValue={1}>
                  <Slider min={0.1} max={1} step={0.1} />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name={['config', 'showWireframe']} label="显示线框" valuePropName="checked" initialValue={false}>
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name={['config', 'castShadow']} label="投射阴影" valuePropName="checked" initialValue={true}>
                  <Switch />
                </Form.Item>
              </Col>
            </Row>

            <Divider orientation="left" plain>标签设置</Divider>

            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name={['config', 'showLabel']} label="显示标签" valuePropName="checked" initialValue={true}>
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name={['config', 'labelFontSize']} label="标签字体大小" initialValue={14}>
                  <InputNumber min={8} max={24} style={{ width: '100%' }} addonAfter="px" />
                </Form.Item>
              </Col>
            </Row>

            <Form.Item name={['config', 'labelPosition']} label="标签位置" initialValue="top">
              <Select>
                <Select.Option value="top">顶部</Select.Option>
                <Select.Option value="bottom">底部</Select.Option>
                <Select.Option value="left">左侧</Select.Option>
                <Select.Option value="right">右侧</Select.Option>
              </Select>
            </Form.Item>

            <Divider orientation="left" plain>数据展示</Divider>

            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name={['config', 'showPowerMeter']} label="显示功率计" valuePropName="checked" initialValue={true}>
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name={['config', 'showTemperature']} label="显示温度计" valuePropName="checked" initialValue={true}>
                  <Switch />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name={['config', 'showVoltage']} label="显示电压表" valuePropName="checked" initialValue={true}>
                  <Switch />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name={['config', 'dataRefreshRate']} label="数据刷新率" initialValue={5}>
                  <Select>
                    <Select.Option value={1}>1秒</Select.Option>
                    <Select.Option value={2}>2秒</Select.Option>
                    <Select.Option value={5}>5秒</Select.Option>
                    <Select.Option value={10}>10秒</Select.Option>
                    <Select.Option value={30}>30秒</Select.Option>
                    <Select.Option value={60}>60秒</Select.Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name={['config', 'dataPrecision']} label="数据精度" initialValue={2}>
                  <Select>
                    <Select.Option value={0}>整数</Select.Option>
                    <Select.Option value={1}>1位小数</Select.Option>
                    <Select.Option value={2}>2位小数</Select.Option>
                    <Select.Option value={3}>3位小数</Select.Option>
                  </Select>
                </Form.Item>
              </Col>
            </Row>

            <Form.Item name={['config', 'dataUnits']} label="数据显示单位" initialValue="si">
              <Select>
                <Select.Option value="si">SI单位 (kW, V, A)</Select.Option>
                <Select.Option value="imperial">英制单位</Select.Option>
                <Select.Option value="custom">自定义</Select.Option>
              </Select>
            </Form.Item>
          </Form>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#999' }}>
            <div style={{ textAlign: 'center' }}>
              <SettingOutlined style={{ fontSize: '48px', marginBottom: '16px' }} />
              <div>请从左侧选择一个设备进行配置</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  // ==================== 高级设置面板 ====================
  const advancedTab = (
    <>
      <Card title="性能优化" size="small" style={{ marginBottom: 16 }}>
        <Form layout="vertical">
          <Form.Item label="渲染质量">
            <Select defaultValue="medium">
              <Select.Option value="low">低质量 (高性能)</Select.Option>
              <Select.Option value="medium">中等质量</Select.Option>
              <Select.Option value="high">高质量</Select.Option>
              <Select.Option value="ultra">超高质量</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item label="阴影质量">
            <Select defaultValue="medium">
              <Select.Option value="low">低 (512×512)</Select.Option>
              <Select.Option value="medium">中 (1024×1024)</Select.Option>
              <Select.Option value="high">高 (2048×2048)</Select.Option>
              <Select.Option value="ultra">超高 (4096×4096)</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item label="抗锯齿">
            <Select defaultValue="fxaa">
              <Select.Option value="none">无</Select.Option>
              <Select.Option value="fxaa">FXAA (快速)</Select.Option>
              <Select.Option value="msaa">MSAA 4x (高质量)</Select.Option>
              <Select.Option value="smaa">SMAA (平衡)</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item label="最大帧率">
            <Slider min={30} max={144} marks={{ 30: '30', 60: '60', 90: '90', 120: '120', 144: '144' }} defaultValue={60} />
          </Form.Item>
          <Form.Item label="GPU 内存限制 (MB)">
            <InputNumber min={256} max={8192} defaultValue={1024} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Card>
      <Card title="数据源设置" size="small">
        <Form layout="vertical">
          <Form.Item label="实时数据源">
            <Select defaultValue="websocket">
              <Select.Option value="websocket">WebSocket (实时)</Select.Option>
              <Select.Option value="polling">轮询 (HTTP)</Select.Option>
              <Select.Option value="mock">模拟数据</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item label="WebSocket 地址">
            <Input placeholder="ws://localhost:8000/ws/v1/digital-twin/global" />
          </Form.Item>
          <Form.Item label="轮询间隔 (秒)">
            <InputNumber min={1} max={60} defaultValue={5} />
          </Form.Item>
          <Form.Item label="数据缓存大小">
            <Select defaultValue="1000">
              <Select.Option value="100">100条</Select.Option>
              <Select.Option value="500">500条</Select.Option>
              <Select.Option value="1000">1000条</Select.Option>
              <Select.Option value="5000">5000条</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item label="历史数据保留 (天)">
            <InputNumber min={1} max={365} defaultValue={30} />
          </Form.Item>
        </Form>
      </Card>
    </>
  );

  return (
    <div className="scene-settings">
      <Tabs
        activeKey={selectedTab}
        onChange={setSelectedTab}
        tabBarExtraContent={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={handleReset} disabled={loading}>重置</Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              onClick={selectedTab === 'general' ? handleSaveScene : handleSaveDevice}
              loading={loading}
            >
              保存
            </Button>
          </Space>
        }
        items={[
          { key: 'general', label: '通用设置', children: generalTab },
          { key: 'devices', label: '设备设置', children: devicesTab },
          { key: 'advanced', label: '高级设置', children: advancedTab },
        ]}
      />
    </div>
  );
};

export default SceneSettings;
