/**
 * 故障诊断页面 - 数据库版
 */
import React, { useState, useEffect } from 'react';
import { 
  Card, Table, Button, Space, Input, Select, Tag, Modal, 
  Row, Col, Statistic, message, Tabs, Typography, Spin, 
  Form, Badge, Tooltip, Progress, Alert
} from 'antd';
import AutoHeightTable from '../../components/AutoHeightTable';
import { 
  SearchOutlined, WarningOutlined, CheckCircleOutlined,
  ReloadOutlined, ToolOutlined, BugOutlined, BarChartOutlined,
  ThunderboltOutlined, BulbOutlined, MedicineBoxOutlined, RobotOutlined
} from '@ant-design/icons';

import AIDiagnosis from './AIDiagnosis';
import { faultDiagnosisAPI, alarmAPI } from '../../api';

const { Option } = Select;
const { Text, Title } = Typography;

interface FaultCode {
  fault_code: string;
  fault_name: string;
  fault_description: string;
  device_type: string;
  fault_category: string;
  fault_level: string;
  response_time_minutes: number;
  auto_stop: boolean;
  remote_fixable: boolean;
  possible_causes: string[];
  diagnosis_steps: string[];
  repair_suggestions: string[];
}

interface Alarm {
  id: number;
  device_id: number;
  device_name: string;
  fault_code: string;
  fault_name: string;
  fault_level: string;
  status: string;
  content: string;
}

const FaultDiagnosisPage: React.FC = () => {
  const [faultCodes, setFaultCodes] = useState<FaultCode[]>([]);
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingAlarms, setLoadingAlarms] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [levelFilter, setLevelFilter] = useState<string>('');
  const [selectedFaultCode, setSelectedFaultCode] = useState<FaultCode | null>(null);
  const [modalVisible, setModalVisible] = useState(false);

  useEffect(() => {
    fetchFaultCodes();
    fetchAlarms();
  }, []);

  const fetchFaultCodes = async () => {
    setLoading(true);
    try {
      const params: any = {};
      if (categoryFilter) params.fault_category = categoryFilter;
      if (levelFilter) params.fault_level = levelFilter;
      
      const response: any = await faultDiagnosisAPI.faultCodes(params);
      setFaultCodes(response.items || []);
    } catch (error: any) {
      message.error('获取故障码列表失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchAlarms = async () => {
    setLoadingAlarms(true);
    try {
      const response: any = await alarmAPI.list();
      setAlarms((response.items || []).filter((a: any) => a.status === 'ACTIVE'));
    } catch (error: any) {
      setAlarms([]);
    } finally {
      setLoadingAlarms(false);
    }
  };

  const handleViewFaultCode = (record: FaultCode) => {
    setSelectedFaultCode(record);
    setModalVisible(true);
  };

  const levelColorMap: Record<string, string> = {
    EMERGENCY: 'red',
    SERIOUS: 'orange',
    WARNING_SERIOUS: 'gold',
    WARNING_GENERAL: 'blue',
  };

  const levelTextMap: Record<string, string> = {
    EMERGENCY: '紧急',
    SERIOUS: '严重',
    WARNING_SERIOUS: '严重告警',
    WARNING_GENERAL: '一般告警',
  };

  const categoryTextMap: Record<string, string> = {
    GRID: '电网侧',
    INVERTER: '逆变侧',
    BATTERY: '电池侧',
    BUS: '母线侧',
    TEMPERATURE: '温度',
    RELAY: '继电器',
    OVERLOAD: '过载',
    OTHER: '其他',
    BCU_BMS: 'BCU/BMS',
    POWER_CONTROL: '功率控制',
    CHARGING_MODULE: '充电模块',
    CHARGING_CONTROLLER: '充电控制器',
    AC_DISTRIBUTION: '交流配电',
    DC_DISTRIBUTION: '直流配电',
    BMS_RELATED: 'BMS相关',
    ENVIRONMENT: '环境安全',
    COMMUNICATION: '通信',
  };

  const faultCodeColumns = [
    { title: '故障码', dataIndex: 'fault_code', key: 'fault_code', width: 100 },
    { title: '故障名称', dataIndex: 'fault_name', key: 'fault_name', width: 150 },
    { 
      title: '故障分类', 
      dataIndex: 'fault_category', 
      key: 'fault_category', 
      width: 100,
      render: (cat: string) => categoryTextMap[cat] || cat,
    },
    { 
      title: '故障等级', 
      dataIndex: 'fault_level', 
      key: 'fault_level', 
      width: 100,
      render: (level: string) => (
        <Tag color={levelColorMap[level]}>{levelTextMap[level] || level}</Tag>
      ),
    },
    { title: '响应时间', dataIndex: 'response_time_minutes', key: 'response_time_minutes', width: 100,
      render: (min: number) => `${min}分钟`,
    },
    { 
      title: '自动停机', 
      dataIndex: 'auto_stop', 
      key: 'auto_stop', 
      width: 80,
      render: (val: boolean) => val ? '是' : '否',
    },
    { 
      title: '远程修复', 
      dataIndex: 'remote_fixable', 
      key: 'remote_fixable', 
      width: 80,
      render: (val: boolean) => val ? '是' : '否',
    },
    { 
      title: '操作', 
      key: 'action', 
      width: 100,
      render: (_: any, record: FaultCode) => (
        <Button type="link" size="small" onClick={() => handleViewFaultCode(record)}>
          查看详情
        </Button>
      ),
    },
  ];

  const alarmColumns = [
    { title: '设备', dataIndex: 'device_name', key: 'device_name', width: 150 },
    { title: '故障码', dataIndex: 'fault_code', key: 'fault_code', width: 100 },
    { title: '故障名称', dataIndex: 'fault_name', key: 'fault_name', width: 150 },
    { 
      title: '故障等级', 
      dataIndex: 'fault_level', 
      key: 'fault_level', 
      width: 100,
      render: (level: string) => (
        <Tag color={levelColorMap[level]}>{levelTextMap[level] || level}</Tag>
      ),
    },
    { title: '内容', dataIndex: 'content', key: 'content', ellipsis: true },
    { 
      title: '状态', 
      dataIndex: 'status', 
      key: 'status', 
      width: 80,
      render: (status: string) => (
        <Tag color="red">{status}</Tag>
      ),
    },
  ];

  return (
    <div className="page-container">
      <Tabs defaultActiveKey="fault-codes">
        <Tabs.TabPane tab="故障码知识库" key="fault-codes">
          <Card title="故障码知识库" extra={
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchFaultCodes}>刷新</Button>
            </Space>
          }>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={8}>
                <Input
                  placeholder="搜索故障码/名称"
                  prefix={<SearchOutlined />}
                  value={searchKeyword}
                  onChange={(e) => setSearchKeyword(e.target.value)}
                  onPressEnter={fetchFaultCodes}
                />
              </Col>
              <Col span={4}>
                <Select
                  style={{ width: '100%' }}
                  placeholder="故障分类"
                  allowClear
                  value={categoryFilter}
                  onChange={(value) => setCategoryFilter(value || '')}
                >
                  <Option value="GRID">电网侧</Option>
                  <Option value="INVERTER">逆变侧</Option>
                  <Option value="BATTERY">电池侧</Option>
                  <Option value="BUS">母线侧</Option>
                  <Option value="TEMPERATURE">温度</Option>
                  <Option value="RELAY">继电器</Option>
                  <Option value="OVERLOAD">过载</Option>
                  <Option value="OTHER">其他</Option>
                </Select>
              </Col>
              <Col span={4}>
                <Select
                  style={{ width: '100%' }}
                  placeholder="故障等级"
                  allowClear
                  value={levelFilter}
                  onChange={(value) => setLevelFilter(value || '')}
                >
                  <Option value="EMERGENCY">紧急</Option>
                  <Option value="SERIOUS">严重</Option>
                  <Option value="WARNING_SERIOUS">严重告警</Option>
                  <Option value="WARNING_GENERAL">一般告警</Option>
                </Select>
              </Col>
              <Col span={4}>
                <Button type="primary" onClick={fetchFaultCodes}>
                  筛选
                </Button>
              </Col>
            </Row>

            <AutoHeightTable
              scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
              columns={faultCodeColumns}
              dataSource={faultCodes.filter(fc => 
                !searchKeyword || 
                fc.fault_code.includes(searchKeyword) ||
                fc.fault_name.includes(searchKeyword) ||
                fc.fault_description.includes(searchKeyword)
              )}
              rowKey="fault_code"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane tab="活跃告警" key="alarms">
          <Card title="活跃告警" extra={
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchAlarms}>刷新</Button>
            </Space>
          }>
            <AutoHeightTable
              scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
              columns={alarmColumns}
              dataSource={alarms}
              rowKey="id"
              loading={loadingAlarms}
              pagination={{ pageSize: 10 }}
            />
          </Card>
        </Tabs.TabPane>

        <Tabs.TabPane tab="AI智能诊断" key="ai-diagnosis">
          <AIDiagnosis />
        </Tabs.TabPane>
      </Tabs>

      {/* 故障码详情弹窗 */}
      <Modal
        title="故障码详情"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={null}
        width={800}
      >
        {selectedFaultCode && (
          <div>
            <h3>{selectedFaultCode.fault_name}</h3>
            <p>{selectedFaultCode.fault_description}</p>
            
            <h4>可能原因</h4>
            <ul>
              {selectedFaultCode.possible_causes?.map((cause, i) => (
                <li key={i}>{cause}</li>
              ))}
            </ul>
            
            <h4>诊断步骤</h4>
            <ol>
              {selectedFaultCode.diagnosis_steps?.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
            
            <h4>修复建议</h4>
            <ul>
              {selectedFaultCode.repair_suggestions?.map((suggestion, i) => (
                <li key={i}>{suggestion}</li>
              ))}
            </ul>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default FaultDiagnosisPage;
