import { useState, useCallback, useEffect, useRef } from 'react';
import { knowledgeApi } from '../services/api';
import { KnowledgeArticle, KnowledgeArticleItem } from '../types';

const mapItem = (it: KnowledgeArticleItem): KnowledgeArticle => ({
  id: it.id,
  title: it.title,
  summary: it.summary,
  content: it.content,
  category: 'other',
  tags: it.tags,
  authorId: 0,
  authorName: it.author,
  viewCount: it.viewCount,
  createdAt: it.createdAt,
  updatedAt: it.updatedAt,
});

interface UseKnowledgeReturn {
  articles: KnowledgeArticle[];
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  searchQuery: string;
  activeCategory: string;
  setSearchQuery: (text: string) => void;
  setActiveCategory: (cat: string) => void;
  fetchArticles: (isRefresh?: boolean) => Promise<void>;
}

export function useKnowledge(): UseKnowledgeReturn {
  const [articles, setArticles] = useState<KnowledgeArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategoryState] = useState('all');
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchArticles = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      let response: { data: { items: KnowledgeArticleItem[] } };
      if (searchQuery.trim()) {
        response = await knowledgeApi.search(searchQuery.trim());
      } else {
        response = await knowledgeApi.getArticles({ page: 1, page_size: 50 });
      }
      setArticles(response.data.items.map(mapItem));
    } catch {
      setError('加载知识库失败，请下拉刷新重试');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [searchQuery]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        let response: { data: { items: KnowledgeArticleItem[] } };
        if (searchQuery.trim()) {
          response = await knowledgeApi.search(searchQuery.trim());
        } else {
          response = await knowledgeApi.getArticles({ page: 1, page_size: 50 });
        }
        if (cancelled) return;
        setArticles(response.data.items.map(mapItem));
      } catch {
        if (!cancelled) setError('加载知识库失败，请下拉刷新重试');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [activeCategory, searchQuery]);

  useEffect(() => {
    return () => {
      if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    };
  }, []);

  const setSearchQueryDebounced = useCallback((text: string) => {
    setSearchQuery(text);
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(() => {
      fetchArticles();
    }, 500);
  }, [fetchArticles]);

  const setActiveCategory = useCallback((cat: string) => {
    setSearchQuery('');
    setActiveCategoryState(cat);
  }, []);

  return {
    articles,
    loading,
    refreshing,
    error,
    searchQuery,
    activeCategory,
    setSearchQuery: setSearchQueryDebounced,
    setActiveCategory,
    fetchArticles,
  };
}
