/**
 * 天链 V3 - 知识库页面类型定义
 */

export interface Article {
  id: number;
  title: string;
  category: string;
  content: string;
  tags?: string;
  view_count?: number;
  created_at: string;
  updated_at?: string;
  author_id?: number;
  author_name?: string;
}

export interface SearchResult {
  id: number;
  title: string;
  category: string;
  summary: string;
  highlight?: string;
  author?: string;
  updated_at?: string;
}

export interface StatsData {
  total: number;
  categories: number;
  total_views: number;
  top_category: string;
}

export interface FAQItem {
  id: number;
  question: string;
  answer: string;
  category: string;
  tags?: string;
  views: number;
  helpful_count: number;
  created_at?: string;
}

export interface CategoryItem {
  id: number;
  name: string;
  icon: string;
  sort_order: number;
  description: string;
  article_count: number;
  created_at?: string;
}
