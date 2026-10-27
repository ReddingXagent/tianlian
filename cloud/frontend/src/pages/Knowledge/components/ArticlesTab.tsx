/**
 * 天链 V3 - 知识库：知识文章 Tab
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card, Space, Button, Input, Select, Empty, List, Tag, Modal,
  Descriptions, Popconfirm,
} from 'antd';
import {
  BookOutlined, PlusOutlined, SearchOutlined, EyeOutlined,
  EditOutlined, DeleteOutlined,
} from '@ant-design/icons';
import Highlight from './Highlight';
import { getTagColor } from '../constants';
import type { KnowledgeBase } from '../hooks/useKnowledgeBase';

const ArticlesTab: React.FC<{ kb: KnowledgeBase }> = ({ kb }) => {
  const navigate = useNavigate();
  const {
    articles, searchText, setSearchText,
    categoryFilter, setCategoryFilter, categories,
    detailVisible, setDetailVisible, selectedArticle,
    handleSearch, fetchArticles, handleDelete,
  } = kb;

  return (
    <>
      <Card
        title={
          <Space>
            <BookOutlined />
            <span>知识库</span>
          </Space>
        }
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/knowledge/create')}>
            创建文章
          </Button>
        }
      >
        <Space style={{ marginBottom: 24, width: '100%' }} size="large">
          <Input.Search
            placeholder="搜索标题或内容"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={handleSearch}
            allowClear
            onClear={() => { setSearchText(''); fetchArticles(); }}
            enterButton={<SearchOutlined />}
            style={{ width: 300 }}
          />
          <Select
            placeholder="按分类筛选"
            value={categoryFilter}
            onChange={(value) => { setCategoryFilter(value); setTimeout(() => fetchArticles(), 0); }}
            allowClear
            style={{ width: 200 }}
          >
            {categories.map(cat => (
              <Select.Option key={cat} value={cat}>{cat}</Select.Option>
            ))}
          </Select>
          <Button onClick={fetchArticles}>刷新</Button>
        </Space>

        {articles.length === 0 ? (
          <Empty description="暂无文章" />
        ) : (
          <List
            itemLayout="vertical"
            dataSource={articles}
            renderItem={(item) => {
              const tags = item.tags ? item.tags.split(',').filter(t => t.trim()) : [];
              return (
                <List.Item
                  key={item.id}
                  actions={[
                    <a key="view" onClick={() => { kb.setSelectedArticle(item); setDetailVisible(true); }}>
                      <EyeOutlined /> 查看
                    </a>,
                    <a key="edit" onClick={() => navigate(`/knowledge/edit/${item.id}`)}>
                      <EditOutlined /> 编辑
                    </a>,
                    <Popconfirm title="确认删除此文章？" onConfirm={() => handleDelete(item.id)} okText="删除" cancelText="取消">
                      <a key="delete" style={{ color: '#ea4335' }}>
                        <DeleteOutlined /> 删除
                      </a>
                    </Popconfirm>,
                  ]}
                  extra={
                    <Space>
                      <Tag color={getTagColor(item.category)}>{item.category}</Tag>
                      {tags.slice(0, 3).map(tag => (
                        <Tag key={tag} color="geekblue">{tag}</Tag>
                      ))}
                    </Space>
                  }
                >
                  <List.Item.Meta
                    title={
                      <a onClick={() => { kb.setSelectedArticle(item); setDetailVisible(true); }}>
                        <Highlight text={item.title} keyword={searchText} />
                      </a>
                    }
                    description={
                      <Space split="|">
                        <span>创建时间: {new Date(item.created_at).toLocaleDateString('zh-CN')}</span>
                        <span>浏览: {item.view_count || 0}</span>
                      </Space>
                    }
                  />
                  <div style={{ marginTop: 8, color: '#666', lineHeight: 1.5 }}>
                    {item.content?.substring(0, 150)}...
                  </div>
                </List.Item>
              );
            }}
          />
        )}
      </Card>

      {/* 文章详情弹窗 */}
      <Modal
        title="文章详情"
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        width={700}
        footer={[
          <Button key="close" onClick={() => setDetailVisible(false)}>关闭</Button>,
          <Button key="edit" type="primary"
            onClick={() => { setDetailVisible(false); if (selectedArticle) navigate(`/knowledge/edit/${selectedArticle.id}`); }}>
            编辑
          </Button>,
        ]}
      >
        {selectedArticle && (
          <div>
            <Descriptions bordered column={1} size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="标题">{selectedArticle.title}</Descriptions.Item>
              <Descriptions.Item label="分类">
                <Tag color={getTagColor(selectedArticle.category)}>{selectedArticle.category}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="标签">
                {selectedArticle.tags ? selectedArticle.tags.split(',').map(t => <Tag key={t}>{t.trim()}</Tag>) : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">{new Date(selectedArticle.created_at).toLocaleString('zh-CN')}</Descriptions.Item>
              <Descriptions.Item label="浏览数">{selectedArticle.view_count || 0}</Descriptions.Item>
            </Descriptions>
            <div style={{ marginTop: 16, padding: 16, background: '#fafafa', borderRadius: 8, lineHeight: 1.8 }}>
              {selectedArticle.content}
            </div>
          </div>
        )}
      </Modal>
    </>
  );
};

export default ArticlesTab;
