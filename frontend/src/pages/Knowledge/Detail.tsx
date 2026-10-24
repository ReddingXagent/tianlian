/**
 * 知识库文章详情页
 */
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Descriptions, Tag, Button, Space, Spin, Alert, Divider, Typography, Popconfirm, message } from 'antd';
import { EditOutlined, DeleteOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { knowledgeAPI } from '../../api';
import DOMPurify from 'dompurify';

const { Title } = Typography;

interface Article {
  id: number;
  title: string;
  category: string;
  content: string;
  tags?: string;
  view_count?: number;
  created_at: string;
  updated_at?: string;
  author_id?: number;
}

const KnowledgeDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [article, setArticle] = useState<Article | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (id) {
      fetchArticle(parseInt(id));
    }
  }, [id]);

  const fetchArticle = async (articleId: number) => {
    setLoading(true);
    setError('');
    try {
      const res: any = await knowledgeAPI.get(articleId);
      // 处理统一响应格式
      const data = res.data?.data || res.data;
      setArticle(data);
    } catch (err: any) {
      setError('加载失败：' + (err.response?.data?.message || err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!article) return;

    try {
      await knowledgeAPI.delete(article.id);
      message.success('文章已删除');
      navigate('/knowledge');
    } catch (err: any) {
      message.error('删除失败：' + (err.response?.data?.message || err.message));
    }
  };

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center' }}><Spin size="large" /></div>;
  }

  if (error) {
    return <Alert message="错误" description={error} type="error" showIcon style={{ margin: 24 }} />;
  }

  if (!article) {
    return <Alert message="未找到文章" type="warning" showIcon style={{ margin: 24 }} />;
  }

  // 解析标签
  const tags = article.tags ? article.tags.split(',').filter(t => t.trim()) : [];

  const getTagColor = (category: string) => {
    const colorMap: Record<string, string> = {
      '维修指南': 'blue',
      '故障诊断': 'red',
      '操作手册': 'green',
      '专家经验': 'purple',
      '安全规范': 'orange',
      'general': 'default',
    };
    return colorMap[category] || 'default';
  };

  return (
    <div className="page-container">
      <Button
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/knowledge')}
        style={{ marginBottom: 16 }}
      >
        返回列表
      </Button>

      <Card>
        <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
          <Title level={2}>{article.title}</Title>
          <Space>
            <Button
              type="primary"
              icon={<EditOutlined />}
              onClick={() => navigate(`/knowledge/edit/${article.id}`)}
            >
              编辑
            </Button>
            <Popconfirm
              title="确定要删除这篇文章吗？"
              onConfirm={handleDelete}
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          </Space>
        </Space>

        <Descriptions bordered column={2} style={{ marginBottom: 24 }}>
          <Descriptions.Item label="分类">
            <Tag color={getTagColor(article.category)}>{article.category}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="标签">
            {tags.length > 0 ? tags.map(tag => (
              <Tag key={tag} color="geekblue">{tag}</Tag>
            )) : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {new Date(article.created_at).toLocaleString('zh-CN')}
          </Descriptions.Item>
          <Descriptions.Item label="更新时间">
            {article.updated_at ? new Date(article.updated_at).toLocaleString('zh-CN') : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="浏览次数">
            {article.view_count || 0}
          </Descriptions.Item>
          <Descriptions.Item label="作者ID">
            {article.author_id || '未知'}
          </Descriptions.Item>
        </Descriptions>

        <Divider>文章内容</Divider>

        <div style={{
          padding: 24,
          background: '#fafafa',
          borderRadius: 4,
          lineHeight: 1.8,
          fontSize: 16
        }}>
          <div className="knowledge-content" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(article.content) }} />
        </div>
      </Card>
    </div>
  );
};

export default KnowledgeDetail;
