/**
 * 知识库文章编辑页 - 富文本编辑器版
 * 使用 react-quill-new 实现富文本编辑
 *
 * 安全注释（卡 5ba7f0d2）：quill 2.0.3 存在 advisory GHSA-v3m3-f69x-jf25（XSS via HTML export），
 * 当前不可达——渲染侧 Detail.tsx / SearchTab.tsx 的 dangerouslySetInnerHTML 均经 DOMPurify.sanitize，
 * 且未使用 getSemanticHTML/getHTML/export 等导出 API。等 upstream quill 补丁后再升级；
 * 勿采用 npm 建议的 react-quill-new@3.7.0 降级方案（破坏性）。
 */
import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Form, Input, Select, Button, Space, Spin, Alert, message } from 'antd';
import { SaveOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import ReactQuill from 'react-quill-new';
import 'react-quill-new/dist/quill.snow.css';
import DOMPurify from 'dompurify';
import { knowledgeAPI } from '../../api';

interface ArticleForm {
  title: string;
  content: string;
  category: string;
  tags?: string;
}

const QuillEditor: React.FC<{ value: string; onChange: (v: string) => void }> = ({ value, onChange }) => {
  const modules = useMemo(() => ({
    toolbar: [
      [{ 'header': [1, 2, 3, 4, 5, 6, false] }],
      ['bold', 'italic', 'underline', 'strike'],
      [{ 'color': [] }, { 'background': [] }],
      [{ 'list': 'ordered' }, { 'list': 'bullet' }, { 'indent': '-1' }, { 'indent': '+1' }],
      ['blockquote', 'code-block'],
      [{ 'align': [] }],
      ['link', 'image'],
      ['clean'],
    ],
  }), []);

  const formats = [
    'header', 'bold', 'italic', 'underline', 'strike',
    'color', 'background',
    'list', 'bullet', 'indent',
    'blockquote', 'code-block',
    'align',
    'link', 'image',
  ];

  return (
    <ReactQuill
      theme="snow"
      value={value}
      onChange={onChange}
      modules={modules}
      formats={formats}
      placeholder="请输入文章内容..."
      style={{ height: 400, marginBottom: 50 }}
    />
  );
};

const KnowledgeEdit: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [content, setContent] = useState('');
  const isEdit = !!id;

  useEffect(() => {
    fetchCategories();
    if (isEdit) {
      fetchArticle(parseInt(id!));
    }
  }, [id]);

  const fetchCategories = async () => {
    try {
      const res: any = await knowledgeAPI.categories();
      // 新接口返回扁平数组
      if (Array.isArray(res.data)) {
        setCategories(res.data);
      } else if (res.data?.categories) {
        // 旧接口兼容
        setCategories(res.data.categories);
      }
    } catch {
      // 静默处理：分类加载失败不阻塞文章编辑
    }
  };

  const fetchArticle = async (articleId: number) => {
    setLoading(true);
    setError('');
    try {
      const res: any = await knowledgeAPI.get(articleId);
      // 处理统一响应格式
      const data = res.data?.data || res.data;
      form.setFieldsValue({
        title: data.title,
        category: data.category,
        tags: data.tags
      });
      if (data.content) setContent(data.content);
    } catch (err: any) {
      setError('加载失败：' + (err.response?.data?.message || err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (values: ArticleForm) => {
    if (!content.trim()) {
      message.warning('请输入文章内容');
      return;
    }
    setSaving(true);
    try {
      // 纵深防御：保存前净化富文本 HTML（剥离 <script>、onerror 等可执行载荷）。
      // 渲染层（Detail.tsx / SearchTab.tsx）已有 DOMPurify 作为主防线，此处确保
      // 写入后端的 content 本身不含脚本，保护移动端等未来消费者（GHSA-v3m3-f69x-jf25）。
      const payload = { ...values, content: DOMPurify.sanitize(content) };
      if (isEdit) {
        await knowledgeAPI.update(parseInt(id!), payload);
        message.success('文章已更新');
        navigate(`/knowledge/detail/${id}`);
      } else {
        const res: any = await knowledgeAPI.create(payload);
        // 处理统一响应格式
        const data = res.data?.data || res.data;
        message.success('文章已创建');
        navigate(`/knowledge/detail/${data.id}`);
      }
    } catch (err: any) {
      message.error('保存失败：' + (err.response?.data?.message || err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div style={{ padding: 40, textAlign: 'center' }}><Spin size="large" /></div>;
  }

  if (error) {
    return <Alert message="错误" description={error} type="error" showIcon style={{ margin: 24 }} />;
  }

  return (
    <div className="page-container">
      <Button
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/knowledge')}
        style={{ marginBottom: 16 }}
      >
        返回列表
      </Button>

      <Card title={isEdit ? '编辑文章' : '创建新文章'}>
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSave}
          initialValues={{ category: '维修指南' }}
        >
          <Form.Item
            name="title"
            label="标题"
            rules={[{ required: true, message: '请输入标题' }]}
          >
            <Input placeholder="请输入文章标题" size="large" />
          </Form.Item>

          <Form.Item
            name="category"
            label="分类"
            rules={[{ required: true, message: '请选择分类' }]}
          >
            <Select placeholder="选择分类" size="large">
              {categories.map(cat => (
                <Select.Option key={cat} value={cat}>{cat}</Select.Option>
              ))}
              <Select.Option value="维修指南">维修指南</Select.Option>
              <Select.Option value="故障诊断">故障诊断</Select.Option>
              <Select.Option value="操作手册">操作手册</Select.Option>
              <Select.Option value="专家经验">专家经验</Select.Option>
              <Select.Option value="安全规范">安全规范</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="tags"
            label="标签"
            help="多个标签用逗号分隔，如：充电桩,故障,维修"
          >
            <Input placeholder="输入标签，用逗号分隔" />
          </Form.Item>

          <Form.Item
            label="内容"
            required
            help="支持富文本编辑：加粗、列表、代码块、链接等"
          >
            <QuillEditor value={content} onChange={setContent} />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button
                type="primary"
                htmlType="submit"
                icon={<SaveOutlined />}
                loading={saving}
                size="large"
              >
                保存
              </Button>
              <Button
                size="large"
                onClick={() => navigate('/knowledge')}
              >
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default KnowledgeEdit;
