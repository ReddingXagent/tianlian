/**
 * 知识库页面 - 增强版（搜索 + 分类筛选 + 统计卡片 + 详情弹窗 + FAQ + 文档生成）
 *
 * 各 Tab UI 拆分至 ./components；数据逻辑见 ./hooks。
 * 文章/分类/搜索/详情/统计存在跨 Tab 共享状态，由 useKnowledgeBase 单实例持有并下发。
 */
import React, { useEffect, useState } from 'react';
import { Spin, Alert, Tabs } from 'antd';
import {
  SearchOutlined, BookOutlined, FolderOutlined,
  QuestionCircleOutlined, FileAddOutlined,
} from '@ant-design/icons';
import { useKnowledgeBase } from './hooks/useKnowledgeBase';
import { useFaq } from './hooks/useFaq';
import { useDocGen } from './hooks/useDocGen';
import StatsCards from './components/StatsCards';
import SearchTab from './components/SearchTab';
import ArticlesTab from './components/ArticlesTab';
import CategoriesTab from './components/CategoriesTab';
import FaqTab from './components/FaqTab';
import DocGenTab from './components/DocGenTab';

const { TabPane } = Tabs;

const Knowledge: React.FC = () => {
  const [activeTab, setActiveTab] = useState('articles');
  const kb = useKnowledgeBase();
  const faq = useFaq();
  const doc = useDocGen();

  useEffect(() => {
    if (activeTab === 'faq') {
      faq.fetchFAQCategories();
      faq.fetchFAQList();
    }
    if (activeTab === 'categories') {
      kb.fetchCategoryItems();
    }
  }, [activeTab]);

  // ===== 主渲染 =====
  if (kb.loading && kb.articles.length === 0 && activeTab === 'articles') {
    return <div style={{ padding: 40, textAlign: 'center' }}><Spin size="large" /></div>;
  }

  if (kb.error) {
    return <Alert message="错误" description={kb.error} type="error" showIcon style={{ margin: 24 }} />;
  }

  return (
    <div className="page-container">
      <StatsCards stats={kb.stats} />

      <Tabs activeKey={activeTab} onChange={setActiveTab} type="card" size="large">
        <TabPane tab={<span><SearchOutlined /> 搜索</span>} key="search">
          <SearchTab kb={kb} />
        </TabPane>
        <TabPane tab={<span><BookOutlined /> 知识文章</span>} key="articles">
          <ArticlesTab kb={kb} />
        </TabPane>
        <TabPane tab={<span><FolderOutlined /> 分类管理</span>} key="categories">
          <CategoriesTab kb={kb} />
        </TabPane>
        <TabPane tab={<span><QuestionCircleOutlined /> FAQ问答</span>} key="faq">
          <FaqTab faq={faq} />
        </TabPane>
        <TabPane tab={<span><FileAddOutlined /> 文档生成</span>} key="docgen">
          <DocGenTab doc={doc} />
        </TabPane>
      </Tabs>
    </div>
  );
};

export default Knowledge;
