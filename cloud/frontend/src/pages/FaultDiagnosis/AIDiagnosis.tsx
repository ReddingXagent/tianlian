/**
 * AI智能诊断面板 - 故障自动触发诊断
 *
 * 功能:
 * - 手动粘贴日志分析
 * - 告警触发诊断结果展示
 * - AI诊断历史记录
 * - AI模型配置管理
 */
import React from 'react';
import { Tabs } from 'antd';
import { FileTextOutlined, HistoryOutlined, SettingOutlined } from '@ant-design/icons';
import ManualLogAnalysis from './components/ManualLogAnalysis';
import DiagnosisHistory from './components/DiagnosisHistory';
import ModelConfig from './components/ModelConfig';

interface AIDiagnosisProps {
  /** 告警ID (从告警诊断页面传入, 自动触发) */
  alarmId?: number | null;
}

const AIDiagnosis: React.FC<AIDiagnosisProps> = ({ alarmId }) => {
  return (
    <Tabs defaultActiveKey="manual">
      <Tabs.TabPane
        tab={<span><FileTextOutlined /> 手动分析</span>}
        key="manual"
      >
        <ManualLogAnalysis />
      </Tabs.TabPane>

      <Tabs.TabPane
        tab={<span><HistoryOutlined /> 诊断历史</span>}
        key="history"
      >
        <DiagnosisHistory />
      </Tabs.TabPane>

      <Tabs.TabPane
        tab={<span><SettingOutlined /> 模型配置</span>}
        key="config"
      >
        <ModelConfig />
      </Tabs.TabPane>
    </Tabs>
  );
};

export default AIDiagnosis;
