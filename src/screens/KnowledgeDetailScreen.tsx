import { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
} from 'react-native';
import { useRoute, RouteProp } from '@react-navigation/native';
import { knowledgeApi } from '../services/api';
import { RootStackParamList, KnowledgeArticle } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';

type DetailRouteProp = RouteProp<RootStackParamList, 'KnowledgeDetail'>;

const KnowledgeDetailScreen: React.FC = () => {
  const route = useRoute<DetailRouteProp>();
  const { articleId } = route.params;
  const [article, setArticle] = useState<KnowledgeArticle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDetail = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // No dedicated detail endpoint; fetch from list and find by id
      const response = await knowledgeApi.getArticles({ page: 1, page_size: 100 });
      const item = response.data.items.find((it) => it.id === articleId);
      if (!item) throw new Error('Article not found');
      setArticle({
        id: item.id,
        title: item.title,
        summary: item.summary,
        content: item.content,
        category: 'other',
        tags: item.tags,
        authorId: 0,
        authorName: item.author,
        viewCount: item.viewCount,
        createdAt: item.createdAt,
        updatedAt: item.updatedAt,
      });
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
        // No dedicated detail endpoint; fetch from list and find by id
        const response = await knowledgeApi.getArticles({ page: 1, page_size: 100 });
        const item = response.data.items.find((it) => it.id === articleId);
        if (!item) throw new Error('Article not found');
        if (cancelled) return;
        setArticle({
          id: item.id,
          title: item.title,
          summary: item.summary,
          content: item.content,
          category: 'other',
          tags: item.tags,
          authorId: 0,
          authorName: item.author,
          viewCount: item.viewCount,
          createdAt: item.createdAt,
          updatedAt: item.updatedAt,
        });
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

  if (loading) {
    return <LoadingSpinner text="加载文章详情..." />;
  }

  if (error || !article) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error || '文章不存在'}
        actionLabel="重新加载"
        onAction={fetchDetail}
      />
    );
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
    >
      {/* 文章头部 */}
      <View style={styles.headerCard}>
        <Text style={styles.title}>{article.title}</Text>
        <View style={styles.meta}>
          <Text style={styles.metaText}>{article.authorName}</Text>
          <Text style={styles.metaDot}>·</Text>
          <Text style={styles.metaText}>
            {new Date(article.createdAt).toLocaleDateString('zh-CN')}
          </Text>
          <Text style={styles.metaDot}>·</Text>
          <Text style={styles.metaText}>{article.viewCount}次浏览</Text>
        </View>
      </View>

      {/* 标签 */}
      {article.tags.length > 0 && (
        <View style={styles.tagRow}>
          {article.tags.map((tag, index) => (
            <View key={index} style={styles.tag}>
              <Text style={styles.tagText}>{tag}</Text>
            </View>
          ))}
        </View>
      )}

      {/* 摘要 */}
      {article.summary ? (
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>📝 摘要</Text>
          <Text style={styles.summaryText}>{article.summary}</Text>
        </View>
      ) : null}

      {/* 正文 */}
      <View style={styles.contentCard}>
        <Text style={styles.contentTitle}>📄 正文</Text>
        <Text style={styles.contentText}>
          {article.content || '暂无详细内容'}
        </Text>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f6fa',
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  headerCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    color: '#333',
    marginBottom: 10,
    lineHeight: 28,
  },
  meta: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  metaText: {
    fontSize: 13,
    color: '#666',
  },
  metaDot: {
    fontSize: 13,
    color: '#ccc',
    marginHorizontal: 6,
  },
  tagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginBottom: 12,
    gap: 6,
  },
  tag: {
    backgroundColor: '#e8f5e9',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 4,
  },
  tagText: {
    fontSize: 12,
    color: '#2e7d32',
  },
  summaryCard: {
    backgroundColor: '#e3f2fd',
    borderRadius: 10,
    padding: 14,
    marginBottom: 12,
  },
  summaryLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1565c0',
    marginBottom: 6,
  },
  summaryText: {
    fontSize: 14,
    color: '#333',
    lineHeight: 22,
  },
  contentCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  contentTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    marginBottom: 12,
  },
  contentText: {
    fontSize: 15,
    color: '#333',
    lineHeight: 26,
  },
});

export default KnowledgeDetailScreen;
