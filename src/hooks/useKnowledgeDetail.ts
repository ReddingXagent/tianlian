import { useState, useCallback, useEffect } from 'react';
import { useRoute, RouteProp } from '@react-navigation/native';
import { knowledgeApi } from '../services/api';
import { RootStackParamList, KnowledgeArticle, KnowledgeArticleItem } from '../types';

type DetailRouteProp = RouteProp<RootStackParamList, 'KnowledgeDetail'>;

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

/**
 * 知识库详情屏数据 hook — 封装文章详情加载、刷新。
 *
 * 职责：
 * - 从路由参数获取 articleId
 * - 从文章列表中查找对应详情（无独立详情端点）
 * - 下拉刷新
 *
 * 返回纯数据 + 操作函数，不包含任何 UI。
 */
export function useKnowledgeDetail() {
  const route = useRoute<DetailRouteProp>();
  const { articleId } = route.params;
  const [article, setArticle] = useState<KnowledgeArticle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDetail = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await knowledgeApi.getArticles({ page: 1, page_size: 100 });
      const item = response.data.items.find((it) => it.id === articleId);
      if (!item) throw new Error('Article not found');
      setArticle(mapItem(item));
    } catch {
      setError('加载文章详情失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [articleId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await knowledgeApi.getArticles({ page: 1, page_size: 100 });
        const item = response.data.items.find((it) => it.id === articleId);
        if (!item) throw new Error('Article not found');
        if (cancelled) return;
        setArticle(mapItem(item));
      } catch {
        if (!cancelled) setError('加载文章详情失败，请重试');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [articleId]);

  return {
    articleId,
    article,
    loading,
    error,
    fetchDetail,
  };
}
