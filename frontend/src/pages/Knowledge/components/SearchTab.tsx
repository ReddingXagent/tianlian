/**
 * 天链 V3 - 知识库：全文搜索 Tab
 */
import React from 'react';
import {
  Card, Space, Input, Empty, List, Tag, Spin, Button, message,
} from 'antd';
import {
  SearchOutlined, EyeOutlined, BookOutlined, TagOutlined,
} from '@ant-design/icons';
import DOMPurify from 'dompurify';
import { knowledgeAPI } from '../../../api';
import { getTagColor } from '../constants';
import type { KnowledgeBase } from '../hooks/useKnowledgeBase';
import type { SearchResult } from '../types';

const SearchTab: React.FC<{ kb: KnowledgeBase }> = ({ kb }) => {
  const {
    searchResults, searchLoading, globalSearchText, setGlobalSearchText,
    searchPerformed, handleGlobalSearch,
    setSelectedArticle, setDetailVisible, fetchStats,
  } = kb;

  return (
    <Card
      title={
        <Space>
          <SearchOutlined />
          <span>全文搜索</span>
        </Space>
      }
    >
      <Space style={{ marginBottom: 24, width: '100%' }} size="large">
        <Input.Search
          placeholder="搜索知识库文章（标题/内容）…"
          value={globalSearchText}
          onChange={(e) => setGlobalSearchText(e.target.value)}
          onSearch={handleGlobalSearch}
          enterButton={<SearchOutlined />}
          size="large"
          style={{ width: 500 }}
          allowClear
        />
        {searchPerformed && (
          <Tag color="blue">{searchResults.length} 条结果</Tag>
        )}
      </Space>

      {searchLoading ? (
        <div style={{ padding: 40, textAlign: 'center' }}><Spin size="large" /></div>
      ) : !searchPerformed ? (
        <Empty description="输入关键词搜索知识库文章">
          <p style={{ color: '#999', fontSize: 13 }}>支持按标题和内容进行关键词全文检索</p>
        </Empty>
      ) : searchResults.length === 0 ? (
        <Empty description={`未找到与"${globalSearchText}"相关的结果`} />
      ) : (
        <List
          itemLayout="vertical"
          dataSource={searchResults}
          renderItem={(item: SearchResult) => (
            <List.Item
              key={item.id}
              actions={[
                <Button
                  key="view"
                  type="link"
                  icon={<EyeOutlined />}
                  onClick={async () => {
                    try {
                      const res: any = await knowledgeAPI.get(item.id);
                      const article = res.data || res;
                      setSelectedArticle({
                        id: article.id,
                        title: article.title,
                        category: article.category,
                        content: article.content,
                        tags: article.tags,
                        view_count: article.view_count,
                        created_at: article.created_at,
                        updated_at: article.updated_at,
                      });
                      setDetailVisible(true);
                      fetchStats();
                    } catch (err) {
                      message.error('加载文章失败');
                    }
                  }}
                >
                  查看详情
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={
                  <div style={{ fontSize: 16, fontWeight: 600 }}>
                    <BookOutlined style={{ marginRight: 8, color: '#ff5a36' }} />
                    {item.title}
                  </div>
                }
                description={
                  <Space split="|" size="middle">
                    <Tag color={getTagColor(item.category)}>{item.category}</Tag>
                    {item.author && (
                      <span><TagOutlined /> {item.author}</span>
                    )}
                    {item.updated_at && (
                      <span>更新于: {new Date(item.updated_at).toLocaleString('zh-CN')}</span>
                    )}
                  </Space>
                }
              />
              {/* 高亮摘要 */}
              <div
                style={{
                  marginTop: 8,
                  padding: '12px 16px',
                  background: '#fffbe6',
                  borderLeft: '3px solid #ff5a36',
                  borderRadius: 4,
                  lineHeight: 1.8,
                  color: '#555',
                }}
                dangerouslySetInnerHTML={{
                  __html: DOMPurify.sanitize(item.summary || item.highlight || '').replace(
                    /<mark>/g,
                    '<span style="background:#fff3b0;padding:0 2px;border-radius:2px">'
                  ).replace(/<\/mark>/g, '</span>'),
                }}
              />
            </List.Item>
          )}
        />
      )}
    </Card>
  );
};

export default SearchTab;
