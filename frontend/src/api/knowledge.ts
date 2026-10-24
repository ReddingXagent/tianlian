/**
 * 知识库 & FAQ & 文档生成 API
 */
import api from './index';

interface FAQItem {
  question: string;
  answer: string;
  category: string;
  tags?: string[];
}

interface DocGenerateRequest {
  doc_type: 'manual' | 'checklist' | 'document';
  device_type?: string;
  fault_code?: string;
  title?: string;
}

interface SearchParams {
  q: string;
  page?: number;
  page_size?: number;
}

export const knowledgeAPI = {
  // 知识库文章 ==========
  /** 列表（支持分页、分类、搜索） */
  list: (params?: { page?: number; page_size?: number; category?: string; search?: string }) =>
    api.get('/knowledge/articles', { params }),
  /** 获取单个文章 */
  get: (id: number) => api.get(`/knowledge/articles/${id}`),
  /** 创建文章 */
  create: (data: Record<string, unknown>) => api.post('/knowledge/articles', data),
  /** 更新文章 */
  update: (id: number, data: Record<string, unknown>) => api.put(`/knowledge/articles/${id}`, data),
  /** 删除文章 */
  delete: (id: number) => api.delete(`/knowledge/articles/${id}`),
  /** 分类列表（新接口，返回扁平数组） */
  categories: () => api.get('/knowledge/categories'),
  /** 创建分类 */
  createCategory: (params: Record<string, unknown>) => api.post('/knowledge/categories', null, { params }),
  /** 更新分类 */
  updateCategory: (id: number, params: Record<string, unknown>) => api.put(`/knowledge/categories/${id}`, null, { params }),
  /** 删除分类 */
  deleteCategory: (id: number) => api.delete(`/knowledge/categories/${id}`),
  /** 分类列表（旧接口兼容） */
  categoriesLegacy: () => api.get('/knowledge/categories/list'),
  /** 统计摘要 */
  stats: () => api.get('/knowledge/stats/summary'),
  /** 全文搜索（标题+内容，返回高亮片段、作者、更新时间） */
  search: (params: SearchParams) => api.get('/knowledge/search', { params }),
};

/** FAQ API */
export const faqAPI = {
  /** 获取FAQ列表（支持分类筛选和关键词搜索） */
  list: (params?: { category?: string; q?: string }) =>
    api.get('/knowledge/faq', { params }),
  /** 创建单个FAQ */
  create: (data: FAQItem) => api.post('/knowledge/faq', data),
  /** 批量导入FAQ */
  batchImport: (faqs: FAQItem[]) =>
    api.post('/knowledge/faq/batch-import', { faqs }),
  /** 标记FAQ有帮助 */
  markHelpful: (faqId: number) =>
    api.put(`/knowledge/faq/${faqId}/helpful`),
  /** 获取FAQ分类列表 */
  categories: () => api.get('/knowledge/faq/categories'),
};

/** 文档生成 API */
export const docAPI = {
  /** 自动生成运维文档markdown */
  generateDoc: (data: DocGenerateRequest) =>
    api.post('/knowledge/generate-doc', data),
};