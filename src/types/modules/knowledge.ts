/**
 * types/modules/knowledge.ts — 知识库相关类型
 */
export type KnowledgeCategory =
  | 'operation'
  | 'maintenance'
  | 'troubleshooting'
  | 'safety'
  | 'regulation'
  | 'other';

export interface KnowledgeArticle {
  id: number;
  title: string;
  summary: string;
  content: string;
  category: KnowledgeCategory;
  tags: string[];
  authorId: number;
  authorName: string;
  viewCount: number;
  createdAt: string;
  updatedAt: string;
}

// 知识库文章 (KnowledgeArticleItem — from /knowledge/articles API)
export interface KnowledgeArticleItem {
  id: number;
  title: string;
  content: string;
  summary: string;
  categoryId: number;
  categoryName?: string;
  tags: string[];
  author: string;
  viewCount: number;
  status: 'published' | 'draft' | 'archived';
  createdAt: string;
  updatedAt: string;
}

// 知识库FAQ条目 (KnowledgeFaqItem — from /knowledge/faq API)
export interface KnowledgeFaqItem {
  id: number;
  question: string;
  answer: string;
  categoryId?: number;
  sortOrder?: number;
}

// 知识库FAQ分类 (FaqCategory — from /knowledge/faq/categories API)
export interface FaqCategory {
  id: number;
  name: string;
  description?: string;
  faqCount?: number;
  sortOrder?: number;
}

// 知识库分类 (KnowledgeCategoryItem — from /knowledge/categories API)
export interface KnowledgeCategoryItem {
  id: number;
  name: string;
  description: string;
  articleCount: number;
  createdAt: string;
  updatedAt: string;
}

// 知识库文章创建 (POST /knowledge/articles)
export interface KnowledgeArticleCreate {
  title: string;
  content: string;
  categoryId?: number;
  tags?: string[];
}

export interface KnowledgeArticleCreated {
  id: number;
  title: string;
  content: string;
  category: string;
  tags: string[] | null;
  viewCount: number;
  published: boolean;
  createdAt: string;
  authorId: number;
}

// 知识库分类创建 (POST /knowledge/categories)
export interface KnowledgeCategoryCreate {
  name: string;
  sortOrder?: number;
  description?: string;
}

export interface KnowledgeCategoryCreated {
  id: number;
  name: string;
  icon: string;
  sortOrder: number;
  description: string;
  createdAt: string;
}

// 知识库分类更新 (PUT /knowledge/categories/{id})
export interface KnowledgeCategoryUpdate {
  name?: string;
  sortOrder?: number;
  description?: string;
}

export interface KnowledgeCategoryUpdated {
  id: number;
  name: string;
  icon: string;
  sortOrder: number;
  description: string;
  createdAt: string;
  updatedAt: string | null;
}

// 知识库文章更新 (PUT /knowledge/articles/{id})
export interface KnowledgeArticleUpdate {
  title?: string;
  content?: string;
  categoryId?: number;
  tags?: string[];
}

export interface KnowledgeArticleUpdated {
  id: number;
  title: string;
  content: string;
  category: string;
  tags: string[] | null;
  viewCount: number;
  published: boolean;
  updatedAt: string;
  authorId: number;
}

// 知识库FAQ创建 (POST /knowledge/faq)
export interface KnowledgeFaqCreate {
  question: string;
  answer: string;
  category: string;
  tags?: string[];
}

export interface KnowledgeFaqCreated {
  id: number;
  question: string;
  answer: string;
  category: string;
  tags: string[] | null;
  views: number;
  helpfulCount: number;
  createdAt: string;
}
