/**
 * 天链 V3 - 知识库：文章/分类/搜索/详情/统计 数据 hook
 *
 * 这些状态存在跨 Tab 共享（文章详情弹窗被 articles/search Tab 共用；
 * categoryItems 同时由 fetchCategories 与 fetchCategoryItems 设置），
 * 因此聚合成单个 hook，由 index 持有单一实例并下发给各 Tab。
 */
import { useEffect, useState } from 'react';
import { message } from 'antd';
import { knowledgeAPI } from '../../../api';
import { fetchAllPages } from '../../../api/fetchAll';
import type { Article, CategoryItem, SearchResult, StatsData } from '../types';

export function useKnowledgeBase() {
  const [loading, setLoading] = useState(false);
  const [articles, setArticles] = useState<Article[]>([]);
  const [error, setError] = useState('');
  const [searchText, setSearchText] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [categories, setCategories] = useState<string[]>([]);
  const [detailVisible, setDetailVisible] = useState(false);
  const [selectedArticle, setSelectedArticle] = useState<Article | null>(null);
  const [stats, setStats] = useState<StatsData>({ total: 0, categories: 0, total_views: 0, top_category: '-' });

  // 分类管理状态
  const [categoryItems, setCategoryItems] = useState<CategoryItem[]>([]);
  const [catManageVisible, setCatManageVisible] = useState(false);
  const [catEditVisible, setCatEditVisible] = useState(false);
  const [editingCategory, setEditingCategory] = useState<CategoryItem | null>(null);
  const [newCatName, setNewCatName] = useState('');
  const [newCatIcon, setNewCatIcon] = useState('');
  const [newCatDesc, setNewCatDesc] = useState('');
  const [newCatSort, setNewCatSort] = useState(0);
  const [catSaving, setCatSaving] = useState(false);

  // 搜索 Tab 状态
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [globalSearchText, setGlobalSearchText] = useState('');
  const [searchPerformed, setSearchPerformed] = useState(false);

  useEffect(() => {
    fetchCategories();
    fetchArticles();
    fetchStats();
  }, []);

  // 全局搜索（搜索 Tab 使用）
  const handleGlobalSearch = async (value: string) => {
    const q = value || globalSearchText;
    if (!q.trim()) {
      message.warning('请输入搜索关键词');
      return;
    }
    setSearchLoading(true);
    setSearchPerformed(true);
    setGlobalSearchText(q);
    try {
      const items = await fetchAllPages<SearchResult>(
        (p) => knowledgeAPI.search({ q, page: p.page as number, page_size: p.page_size as number }),
      );
      setSearchResults(items);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '未知错误';
      message.error('搜索失败：' + msg);
    } finally {
      setSearchLoading(false);
    }
  };

  // 搜索时使用专用的 /search 端点
  const handleSearch = async (value: string) => {
    if (!value.trim()) {
      fetchArticles();
      return;
    }
    setLoading(true);
    setError('');
    try {
      const searchResults = await fetchAllPages<any>(
        (p) => knowledgeAPI.search({ q: value, page: p.page as number, page_size: p.page_size as number }),
      );
      // 将搜索结果提取出来用于主列表展示
      const articleResults = searchResults
        .map((r: any) => ({
          id: r.id,
          title: r.title,
          category: r.category,
          content: r.summary || r.highlight || '',
          created_at: r.updated_at || new Date().toISOString(),
          updated_at: r.updated_at,
          view_count: 0,
        }));
      setArticles(articleResults);
      setSearchText(value);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '未知错误';
      setError('搜索失败：' + msg);
    } finally {
      setLoading(false);
    }
  };

  const fetchCategories = async () => {
    try {
      const res: any = await knowledgeAPI.categories();
      const data = res.data;
      if (Array.isArray(data)) {
        // 新接口返回对象数组
        setCategories(data.map((c: any) => c.name));
        setCategoryItems(data);
      } else if (data?.categories) {
        setCategories(data.categories);
      }
    } catch {
      // 静默处理：分类加载失败不阻塞文章列表
    }
  };

  const fetchCategoryItems = async () => {
    try {
      const res: any = await knowledgeAPI.categories();
      const data = res.data;
      if (Array.isArray(data)) {
        setCategoryItems(data);
      }
    } catch {
      // 静默处理：分类项加载失败保留上次值
    }
  };

  const handleCreateCategory = async () => {
    if (!newCatName.trim()) { message.warning('请输入分类名称'); return; }
    setCatSaving(true);
    try {
      await knowledgeAPI.createCategory({ name: newCatName, icon: newCatIcon, description: newCatDesc, sort_order: newCatSort });
      message.success('分类创建成功');
      setCatEditVisible(false);
      setNewCatName(''); setNewCatIcon(''); setNewCatDesc(''); setNewCatSort(0);
      fetchCategoryItems();
      fetchCategories();
    } catch (err: any) {
      message.error('创建失败：' + (err.response?.data?.detail || err.message));
    } finally {
      setCatSaving(false);
    }
  };

  const handleUpdateCategory = async () => {
    if (!editingCategory || !newCatName.trim()) { message.warning('请输入分类名称'); return; }
    setCatSaving(true);
    try {
      await knowledgeAPI.updateCategory(editingCategory.id, { name: newCatName, icon: newCatIcon, description: newCatDesc, sort_order: newCatSort });
      message.success('分类更新成功');
      setCatEditVisible(false);
      setEditingCategory(null);
      setNewCatName(''); setNewCatIcon(''); setNewCatDesc(''); setNewCatSort(0);
      fetchCategoryItems();
      fetchCategories();
    } catch (err: any) {
      message.error('更新失败：' + (err.response?.data?.detail || err.message));
    } finally {
      setCatSaving(false);
    }
  };

  const handleDeleteCategory = async (catId: number) => {
    try {
      await knowledgeAPI.deleteCategory(catId);
      message.success('分类已删除');
      fetchCategoryItems();
      fetchCategories();
    } catch (err: any) {
      message.error('删除失败：' + (err.response?.data?.detail || err.message));
    }
  };

  const openEditCategory = (cat: CategoryItem) => {
    setEditingCategory(cat);
    setNewCatName(cat.name);
    setNewCatIcon(cat.icon || '');
    setNewCatDesc(cat.description || '');
    setNewCatSort(cat.sort_order || 0);
    setCatEditVisible(true);
  };

  const openCreateCategory = () => {
    setEditingCategory(null);
    setNewCatName('');
    setNewCatIcon('');
    setNewCatDesc('');
    setNewCatSort(0);
    setCatEditVisible(true);
  };

  const fetchStats = async () => {
    try {
      const res: any = await knowledgeAPI.stats();
      if (res.data) {
        const d = res.data as any;
        setStats({
          total: d.total || 0,
          categories: d.categories || 0,
          total_views: d.total_views || 0,
          top_category: d.top_category || '-',
        });
      }
    } catch {
      // 静默处理：统计加载失败保留上次值
    }
  };

  const fetchArticles = async () => {
    setLoading(true);
    setError('');
    try {
      const extraParams: Record<string, unknown> = {};
      if (categoryFilter) extraParams.category = categoryFilter;
      if (searchText) extraParams.search = searchText;
      const items = await fetchAllPages<Article>(
        (p) => knowledgeAPI.list(p as { page?: number; page_size?: number; category?: string; search?: string }),
        extraParams,
      );
      setArticles(items);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '未知错误';
      setError('加载失败：' + msg);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await knowledgeAPI.delete(id);
      message.success('文章已删除');
      fetchArticles();
      fetchStats();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '未知错误';
      message.error('删除失败：' + msg);
    }
  };

  return {
    loading, articles, error, searchText, setSearchText,
    categoryFilter, setCategoryFilter, categories,
    detailVisible, setDetailVisible, selectedArticle, setSelectedArticle,
    stats,
    categoryItems, catManageVisible, setCatManageVisible,
    catEditVisible, setCatEditVisible, editingCategory, setEditingCategory,
    newCatName, setNewCatName, newCatIcon, setNewCatIcon,
    newCatDesc, setNewCatDesc, newCatSort, setNewCatSort, catSaving,
    searchResults, searchLoading, globalSearchText, setGlobalSearchText,
    searchPerformed,
    fetchCategories, fetchCategoryItems, fetchArticles, fetchStats,
    handleSearch, handleDelete, handleGlobalSearch,
    handleCreateCategory, handleUpdateCategory, handleDeleteCategory,
    openEditCategory, openCreateCategory,
  };
}

export type KnowledgeBase = ReturnType<typeof useKnowledgeBase>;
