/**
 * 天链 V3 — 发票管理主页 (Tab: 待审核 / 已开发票 / 抬头管理 / 开票平台设置)
 *
 * 卡 6d06831d (B1 下线旧 OpsInvoice): 待审核 Tab 只留 ManualInvoiceRequests
 * (InvoiceRequest 新体系 pending 列表 + upload/reject), 旧 PendingInvoices 页已删。
 */
import React, { useState } from 'react';
import { Tabs } from 'antd';
import { AuditOutlined, FileTextOutlined, ContactsOutlined, ApiOutlined } from '@ant-design/icons';
import ManualInvoiceRequestsPage from './ManualInvoiceRequests';
import IssuedInvoicesPage from './IssuedInvoices';
import InvoiceTitlesPage from './InvoiceTitles';
import InvoicePlatformPage from './InvoicePlatforms';

const InvoicesIndex: React.FC = () => {
  const [activeTab, setActiveTab] = useState('pending');

  return (
    <Tabs
      activeKey={activeTab}
      onChange={setActiveTab}
      items={[
        {
          key: 'pending',
          label: <span><AuditOutlined /> 待审核</span>,
          children: <ManualInvoiceRequestsPage />,
        },
        {
          key: 'issued',
          label: <span><FileTextOutlined /> 已开发票</span>,
          children: <IssuedInvoicesPage />,
        },
        {
          key: 'titles',
          label: <span><ContactsOutlined /> 发票抬头</span>,
          children: <InvoiceTitlesPage />,
        },
        {
          key: 'platforms',
          label: <span><ApiOutlined /> 开票平台设置</span>,
          children: <InvoicePlatformPage />,
        },
      ]}
    />
  );
};

export default InvoicesIndex;
